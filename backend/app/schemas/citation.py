from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel

from app.models.citation import CitationType


class CitationBase(BaseModel):
    """Base citation schema."""
    id: UUID
    citation_type: CitationType
    title: Optional[int] = None
    section: str
    subsection: Optional[str] = None
    raw_text: str
    statute_fetched: bool = False

    class Config:
        from_attributes = True


class CitationDetail(CitationBase):
    """Citation with additional details."""
    position_start: Optional[int] = None
    position_end: Optional[int] = None
    context_text: Optional[str] = None
    canonical_citation: Optional[str] = None


class CitationListResponse(BaseModel):
    """Response for listing citations."""
    document_id: UUID
    citations: List[CitationBase]
    total: int


class CitationFetchResponse(BaseModel):
    """Response after fetching a statute for a citation."""
    citation_id: UUID
    statute_fetched: bool
    statute_heading: Optional[str] = None
    message: str
