"""
Comparison API endpoints

Handles generating and retrieving redline comparisons.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models import Document, DocumentStatus, Citation, Comparison, AmendmentType
from app.schemas import ComparisonListResponse, ComparisonBase, CompareRequest
from app.services import AmendmentParser, AmendmentApplier, DiffGenerator, generate_redline_html, SubsectionExtractor
from app.services.amendment_parser import AmendmentType as ParsedAmendmentType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["comparisons"])

# Initialize services
amendment_parser = AmendmentParser()
amendment_applier = AmendmentApplier()
diff_generator = DiffGenerator()
subsection_extractor = SubsectionExtractor()


def _extract_subsection_notation(section: str) -> str:
    """
    Extract subsection notation from a section string.

    Examples:
        "1922(b)(1)" -> "(b)(1)"
        "1923(a)" -> "(a)"
        "501" -> ""
    """
    import re
    # Find all parenthetical parts
    match = re.search(r'(\([^)]+\))+', section)
    if match:
        return match.group(0)
    return ""


def _get_target_text_for_amendment(
    full_statute_text: str,
    section: str,
    parsed_amendment
) -> tuple:
    """
    Get the appropriate text to apply an amendment to.

    If the amendment targets a specific subparagraph, extract that portion.
    Otherwise, use the subsection from the citation or the full text.

    Returns:
        (target_text, subsection_notation, is_subsection)
    """
    # Check if the parsed amendment has a target section (e.g., "subparagraph (D)")
    if parsed_amendment and parsed_amendment.target_section:
        # Extract the target notation from the amendment
        import re
        target_match = re.search(r'\(([A-Za-z0-9]+)\)', parsed_amendment.target_section)
        if target_match:
            target_notation = f"({target_match.group(1)})"
            result = subsection_extractor.extract(full_statute_text, target_notation)
            if result.success and result.extracted_text:
                return result.extracted_text, target_notation, True

    # Try to extract from the citation's subsection notation
    subsection_notation = _extract_subsection_notation(section)
    if subsection_notation:
        result = subsection_extractor.extract(full_statute_text, subsection_notation)
        if result.success and result.extracted_text:
            return result.extracted_text, subsection_notation, True

    # Fall back to full text
    return full_statute_text, "", False


@router.post("/{document_id}/compare")
async def generate_comparisons(
    document_id: UUID,
    request: CompareRequest = CompareRequest(),
    db: AsyncSession = Depends(get_db)
):
    """
    Generate redline comparisons for a document.

    Analyzes each citation's context to detect amendments, then applies
    changes to the original statute text and generates diff HTML.
    """
    # Get document with citations
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.citations))
        .options(selectinload(Document.comparisons))
        .where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    if document.status not in [DocumentStatus.PARSED, DocumentStatus.COMPLETED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document must be parsed before comparison"
        )

    # Check if all citations have statutes fetched
    unfetched = [c for c in document.citations if not c.statute_fetched]
    if unfetched:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{len(unfetched)} citation(s) need statute text fetched first"
        )

    # Delete existing comparisons if force_refresh
    if request.force_refresh and document.comparisons:
        for comp in document.comparisons:
            await db.delete(comp)
        await db.flush()

    # Skip if comparisons already exist
    if document.comparisons and not request.force_refresh:
        return {
            "document_id": document.id,
            "message": "Comparisons already exist",
            "comparisons_count": len(document.comparisons)
        }

    document.status = DocumentStatus.PROCESSING
    await db.commit()

    try:
        comparisons_created = 0
        skipped_definitional = 0

        for citation in document.citations:
            # Get the statute text
            statute_result = await db.execute(
                select(Statute).where(Statute.id == citation.statute_id)
            )
            statute = statute_result.scalar_one_or_none()

            if not statute:
                continue

            # Parse amendments from the citation context
            context_text = citation.context_text or ""

            # Check if this is a definitional reference (not an actual amendment)
            if amendment_parser.is_definitional_reference(context_text) and not amendment_parser.is_amendment_context(context_text):
                logger.info(f"Skipping definitional reference for {citation.canonical_citation}")
                skipped_definitional += 1
                # Still create a comparison record but mark it as definitional
                comparison = Comparison(
                    document_id=document.id,
                    citation_id=citation.id,
                    citation_text=citation.canonical_citation,
                    amendment_type=AmendmentType.UNKNOWN,
                    amendment_instruction="(Definitional reference - no amendment)",
                    original_text=statute.full_text[:2000],  # Truncate for definitional refs
                    amended_text=statute.full_text[:2000],
                    diff_html=f'<div class="redline-container"><p class="redline-note">This citation is a definitional reference. The statute is shown for context but no amendments were detected.</p><div class="redline-content">{statute.full_text[:2000]}...</div></div>',
                )
                db.add(comparison)
                comparisons_created += 1
                continue

            parse_result = amendment_parser.parse(context_text)

            # Determine amendment type and apply changes
            full_statute_text = statute.full_text
            amendment_type = AmendmentType.UNKNOWN
            amendment_instruction = ""
            subsection_notation = ""
            used_subsection = False

            if parse_result.success and parse_result.amendments:
                # Use the first valid amendment found
                for parsed in parse_result.amendments:
                    if parsed.is_valid:
                        # Map parsed type to model type
                        amendment_type = _map_amendment_type(parsed.amendment_type)
                        amendment_instruction = parsed.raw_instruction

                        # Get the target text (subsection or full text)
                        target_text, subsection_notation, used_subsection = _get_target_text_for_amendment(
                            full_statute_text,
                            citation.section,
                            parsed
                        )

                        if used_subsection:
                            logger.info(f"Extracted subsection {subsection_notation} for {citation.canonical_citation}")

                        # Apply the amendment to the target text
                        amended_text, success = amendment_applier.apply(target_text, parsed)

                        if success:
                            logger.info(f"Applied {amendment_type.value} amendment for {citation.canonical_citation}")
                            # Use subsection text for comparison (cleaner diff)
                            original_text = target_text
                        else:
                            logger.warning(f"Could not apply amendment for {citation.canonical_citation}")
                            # Fall back to full text
                            original_text = full_statute_text
                            amended_text = full_statute_text
                        break
                else:
                    # No valid amendments found
                    original_text = full_statute_text
                    amended_text = full_statute_text
            else:
                # Fallback to keyword detection
                amendment_type = _detect_amendment_type(context_text)

                # Still try to extract subsection for better context
                subsection_notation = _extract_subsection_notation(citation.section)
                if subsection_notation:
                    result = subsection_extractor.extract(full_statute_text, subsection_notation)
                    if result.success and result.extracted_text:
                        original_text = result.extracted_text
                        amended_text = result.extracted_text
                        used_subsection = True
                    else:
                        original_text = full_statute_text
                        amended_text = full_statute_text
                else:
                    original_text = full_statute_text
                    amended_text = full_statute_text

            # Generate diff HTML using diff-match-patch
            diff_result = diff_generator.generate(original_text, amended_text, max_length=5000)

            # Add subsection context to diff if used
            subsection_info = f" (subsection {subsection_notation})" if used_subsection else ""
            diff_html = generate_redline_html(
                original_text, amended_text,
                amendment_type=amendment_type.value + subsection_info,
                max_length=5000
            )

            # Create comparison record
            comparison = Comparison(
                document_id=document.id,
                citation_id=citation.id,
                citation_text=citation.canonical_citation,
                amendment_type=amendment_type,
                amendment_instruction=amendment_instruction[:500] if amendment_instruction else None,
                original_text=original_text,
                amended_text=amended_text,
                diff_html=diff_html,
            )
            db.add(comparison)
            comparisons_created += 1

        document.status = DocumentStatus.COMPLETED
        await db.commit()

        logger.info(f"Generated {comparisons_created} comparisons for document {document_id} ({skipped_definitional} definitional references)")

        return {
            "document_id": document.id,
            "message": f"Generated {comparisons_created} comparisons ({skipped_definitional} definitional references)",
            "comparisons_count": comparisons_created,
            "definitional_references": skipped_definitional
        }

    except Exception as e:
        logger.error(f"Error generating comparisons for document {document_id}: {e}")
        document.status = DocumentStatus.FAILED
        document.error_message = str(e)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate comparisons: {str(e)}"
        )


@router.get("/{document_id}/result", response_model=ComparisonListResponse)
async def get_comparison_results(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all comparison results for a document.
    """
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.comparisons))
        .where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    comparisons = [
        ComparisonBase(
            id=c.id,
            citation_text=c.citation_text,
            amendment_type=c.amendment_type,
            original_text=c.original_text,
            amended_text=c.amended_text,
            diff_html=c.diff_html,
        )
        for c in document.comparisons
    ]

    return ComparisonListResponse(
        document_id=document.id,
        document_filename=document.filename,
        comparisons=comparisons,
        total=len(comparisons)
    )


# Import Statute model for the endpoint
from app.models import Statute


def _map_amendment_type(parsed_type: ParsedAmendmentType) -> AmendmentType:
    """Map parsed amendment type to model amendment type."""
    mapping = {
        ParsedAmendmentType.STRIKE_INSERT: AmendmentType.STRIKE_INSERT,
        ParsedAmendmentType.INSERT_AFTER: AmendmentType.INSERT_AFTER,
        ParsedAmendmentType.INSERT_BEFORE: AmendmentType.INSERT_AFTER,  # Map to INSERT_AFTER
        ParsedAmendmentType.READ_AS_FOLLOWS: AmendmentType.READ_AS_FOLLOWS,
        ParsedAmendmentType.ADD_AT_END: AmendmentType.ADD_AT_END,
        ParsedAmendmentType.ADD_AT_BEGINNING: AmendmentType.ADD_AT_END,  # Map to ADD_AT_END
        ParsedAmendmentType.STRIKE: AmendmentType.STRIKE,
        ParsedAmendmentType.REDESIGNATE: AmendmentType.STRIKE_INSERT,  # Treat as strike/insert
        ParsedAmendmentType.UNKNOWN: AmendmentType.UNKNOWN,
    }
    return mapping.get(parsed_type, AmendmentType.UNKNOWN)


def _detect_amendment_type(context: str) -> AmendmentType:
    """Detect the amendment type from surrounding context (fallback)."""
    context_lower = context.lower()

    if "striking" in context_lower and "inserting" in context_lower:
        return AmendmentType.STRIKE_INSERT
    elif "inserting after" in context_lower:
        return AmendmentType.INSERT_AFTER
    elif "read as follows" in context_lower:
        return AmendmentType.READ_AS_FOLLOWS
    elif "adding at the end" in context_lower:
        return AmendmentType.ADD_AT_END
    elif "striking" in context_lower:
        return AmendmentType.STRIKE
    else:
        return AmendmentType.UNKNOWN


