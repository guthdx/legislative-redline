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
from app.services import AmendmentParser, AmendmentApplier, DiffGenerator, generate_redline_html
from app.services.amendment_parser import AmendmentType as ParsedAmendmentType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["comparisons"])

# Initialize services
amendment_parser = AmendmentParser()
amendment_applier = AmendmentApplier()
diff_generator = DiffGenerator()


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
            parse_result = amendment_parser.parse(context_text)

            # Determine amendment type and apply changes
            original_text = statute.full_text
            amended_text = original_text
            amendment_type = AmendmentType.UNKNOWN
            amendment_instruction = ""

            if parse_result.success and parse_result.amendments:
                # Use the first valid amendment found
                for parsed in parse_result.amendments:
                    if parsed.is_valid:
                        # Map parsed type to model type
                        amendment_type = _map_amendment_type(parsed.amendment_type)
                        amendment_instruction = parsed.raw_instruction

                        # Apply the amendment to get amended text
                        amended_text, success = amendment_applier.apply(original_text, parsed)
                        if success:
                            logger.info(f"Applied {amendment_type.value} amendment for {citation.canonical_citation}")
                        else:
                            logger.warning(f"Could not apply amendment for {citation.canonical_citation}")
                        break
            else:
                # Fallback to keyword detection
                amendment_type = _detect_amendment_type(context_text)

            # Generate diff HTML using diff-match-patch
            diff_result = diff_generator.generate(original_text, amended_text, max_length=5000)
            diff_html = generate_redline_html(
                original_text, amended_text,
                amendment_type=amendment_type.value,
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

        logger.info(f"Generated {comparisons_created} comparisons for document {document_id}")

        return {
            "document_id": document.id,
            "message": f"Generated {comparisons_created} comparisons",
            "comparisons_count": comparisons_created
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


