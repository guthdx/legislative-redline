"""
Citation API endpoints

Handles fetching statute text for citations.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.session import get_db
from app.models import Citation, Statute, StatuteSource
from app.schemas import CitationFetchResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/citations", tags=["citations"])


@router.post("/{citation_id}/fetch-statute", response_model=CitationFetchResponse)
async def fetch_statute_for_citation(
    citation_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Fetch the current statute text for a citation.

    Retrieves the official text from govinfo.gov (USC) or eCFR.gov (CFR)
    and caches it for future use.
    """
    # Get citation
    result = await db.execute(
        select(Citation).where(Citation.id == citation_id)
    )
    citation = result.scalar_one_or_none()

    if not citation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Citation not found"
        )

    # Check if statute already exists in cache
    existing_result = await db.execute(
        select(Statute).where(
            Statute.citation_type == citation.citation_type.value,
            Statute.title == citation.title,
            Statute.section == citation.section,
        )
    )
    existing_statute = existing_result.scalar_one_or_none()

    if existing_statute and not existing_statute.is_expired:
        # Use cached statute
        citation.statute_id = existing_statute.id
        citation.statute_fetched = True
        await db.commit()

        logger.info(f"Using cached statute for citation {citation_id}")

        return CitationFetchResponse(
            citation_id=citation.id,
            statute_fetched=True,
            statute_heading=existing_statute.heading,
            message="Statute retrieved from cache"
        )

    # TODO: Implement actual API calls to govinfo.gov and eCFR.gov
    # For now, create a placeholder statute

    try:
        # Determine source based on citation type
        if citation.citation_type.value == "usc":
            source = StatuteSource.GOVINFO
            source_url = f"https://www.govinfo.gov/link/uscode/{citation.title}/{citation.section}"
            # Placeholder text - will be replaced with actual API call
            full_text = f"[Placeholder: {citation.title} U.S.C. § {citation.section}]\n\nThis is placeholder text. In the full implementation, this will be fetched from govinfo.gov API."
            heading = f"Section {citation.section}"
        elif citation.citation_type.value == "cfr":
            source = StatuteSource.ECFR
            source_url = f"https://www.ecfr.gov/current/title-{citation.title}/section-{citation.section}"
            full_text = f"[Placeholder: {citation.title} C.F.R. § {citation.section}]\n\nThis is placeholder text. In the full implementation, this will be fetched from eCFR.gov API."
            heading = f"Section {citation.section}"
        else:
            source = StatuteSource.MANUAL
            source_url = None
            full_text = f"[Public Law {citation.title}-{citation.section}]\n\nPublic law text is not available through automated APIs."
            heading = f"Public Law {citation.title}-{citation.section}"

        # Create or update statute
        if existing_statute:
            existing_statute.full_text = full_text
            existing_statute.heading = heading
            existing_statute.source = source
            existing_statute.source_url = source_url
            statute = existing_statute
        else:
            statute = Statute(
                citation_type=citation.citation_type.value,
                title=citation.title,
                section=citation.section,
                full_text=full_text,
                heading=heading,
                source=source,
                source_url=source_url,
            )
            db.add(statute)
            await db.flush()

        # Link citation to statute
        citation.statute_id = statute.id
        citation.statute_fetched = True
        await db.commit()

        logger.info(f"Statute fetched for citation {citation_id}")

        return CitationFetchResponse(
            citation_id=citation.id,
            statute_fetched=True,
            statute_heading=heading,
            message="Statute fetched successfully (placeholder - API integration pending)"
        )

    except Exception as e:
        logger.error(f"Error fetching statute for citation {citation_id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch statute: {str(e)}"
        )


@router.get("/{citation_id}")
async def get_citation(
    citation_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get citation details.
    """
    result = await db.execute(
        select(Citation).where(Citation.id == citation_id)
    )
    citation = result.scalar_one_or_none()

    if not citation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Citation not found"
        )

    return {
        "id": citation.id,
        "document_id": citation.document_id,
        "citation_type": citation.citation_type,
        "title": citation.title,
        "section": citation.section,
        "subsection": citation.subsection,
        "raw_text": citation.raw_text,
        "canonical_citation": citation.canonical_citation,
        "statute_fetched": citation.statute_fetched,
        "context_text": citation.context_text[:500] if citation.context_text else None,
    }
