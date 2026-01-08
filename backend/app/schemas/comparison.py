from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel

from app.models.comparison import AmendmentType


class ComparisonBase(BaseModel):
    """Base comparison schema."""
    id: UUID
    citation_text: Optional[str] = None
    amendment_type: Optional[AmendmentType] = None
    original_text: Optional[str] = None
    amended_text: Optional[str] = None
    diff_html: Optional[str] = None

    class Config:
        from_attributes = True


class ComparisonDetail(ComparisonBase):
    """Comparison with additional details."""
    citation_id: Optional[UUID] = None
    amendment_instruction: Optional[str] = None
    created_at: datetime


class ComparisonListResponse(BaseModel):
    """Response for document comparison results."""
    document_id: UUID
    document_filename: str
    comparisons: List[ComparisonBase]
    total: int


class CompareRequest(BaseModel):
    """Request to generate comparisons for a document."""
    force_refresh: bool = False  # Re-generate even if comparisons exist
