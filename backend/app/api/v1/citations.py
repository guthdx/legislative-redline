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
from app.services import StatuteFetcherService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/citations", tags=["citations"])

# Initialize the statute fetcher service
statute_fetcher = StatuteFetcherService()


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

    try:
        # Fetch from official API
        fetched = await statute_fetcher.fetch(
            citation_type=citation.citation_type.value,
            title=citation.title,
            section=citation.section
        )

        if not fetched.success:
            # Return error but don't fail - citation stays unfetched
            logger.warning(f"Failed to fetch statute for {citation_id}: {fetched.error_message}")
            return CitationFetchResponse(
                citation_id=citation.id,
                statute_fetched=False,
                statute_heading=None,
                message=f"Could not fetch statute: {fetched.error_message}"
            )

        # Determine source based on citation type
        if citation.citation_type.value == "usc":
            source = StatuteSource.GOVINFO
        elif citation.citation_type.value == "cfr":
            source = StatuteSource.ECFR
        else:
            source = StatuteSource.MANUAL

        # Create or update statute in cache
        if existing_statute:
            existing_statute.full_text = fetched.full_text
            existing_statute.heading = fetched.heading
            existing_statute.source = source
            existing_statute.source_url = fetched.source_url
            statute = existing_statute
        else:
            statute = Statute(
                citation_type=citation.citation_type.value,
                title=citation.title,
                section=citation.section,
                full_text=fetched.full_text,
                heading=fetched.heading,
                source=source,
                source_url=fetched.source_url,
            )
            db.add(statute)
            await db.flush()

        # Link citation to statute
        citation.statute_id = statute.id
        citation.statute_fetched = True
        await db.commit()

        logger.info(f"Statute fetched for citation {citation_id} from {source.value}")

        return CitationFetchResponse(
            citation_id=citation.id,
            statute_fetched=True,
            statute_heading=fetched.heading,
            message=f"Statute fetched successfully from {source.value}"
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
