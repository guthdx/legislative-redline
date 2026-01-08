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

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["comparisons"])


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

            # TODO: Implement actual amendment parsing and diff generation
            # For now, create placeholder comparisons

            # Detect amendment type from context
            amendment_type = _detect_amendment_type(citation.context_text or "")

            # Create placeholder comparison
            comparison = Comparison(
                document_id=document.id,
                citation_id=citation.id,
                citation_text=citation.canonical_citation,
                amendment_type=amendment_type,
                original_text=statute.full_text,
                amended_text=statute.full_text,  # Placeholder - will be modified
                diff_html=_generate_placeholder_diff(statute.full_text, amendment_type),
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


def _detect_amendment_type(context: str) -> AmendmentType:
    """Detect the amendment type from surrounding context."""
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


def _generate_placeholder_diff(original_text: str, amendment_type: AmendmentType) -> str:
    """Generate placeholder diff HTML."""
    # In full implementation, this will use diff-match-patch

    if amendment_type == AmendmentType.UNKNOWN:
        return f'<span class="redline-unchanged">{original_text}</span>'

    # For now, just wrap the text to show it's been processed
    return f'''
<div class="redline-section">
    <p class="text-sm text-gray-500 mb-2">Amendment type: {amendment_type.value}</p>
    <div class="redline-content">
        <span class="redline-unchanged">{original_text[:200]}...</span>
        <span class="text-gray-400">[Full diff generation pending API integration]</span>
    </div>
</div>
'''
