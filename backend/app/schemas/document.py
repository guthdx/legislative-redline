from datetime import datetime
from typing import Optional, List
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.document import DocumentStatus


class DocumentUploadResponse(BaseModel):
    """Response after uploading a document."""
    id: UUID
    filename: str
    file_type: str
    status: DocumentStatus
    created_at: datetime

    class Config:
        from_attributes = True


class DocumentParseResponse(BaseModel):
    """Response after parsing a document."""
    id: UUID
    status: DocumentStatus
    citations_found: int
    message: str


class DocumentBase(BaseModel):
    """Base document schema."""
    id: UUID
    filename: str
    file_type: str
    status: DocumentStatus
    created_at: datetime
    expires_at: datetime
    error_message: Optional[str] = None

    class Config:
        from_attributes = True


class DocumentDetail(DocumentBase):
    """Detailed document with citations count."""
    citations_count: int = 0
    comparisons_count: int = 0
