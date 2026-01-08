"""
Document API endpoints

Handles document upload, parsing, and citation detection.
"""

import logging
import shutil
from pathlib import Path
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.core.config import settings
from app.models import Document, DocumentStatus, Citation, CitationType
from app.schemas import (
    DocumentUploadResponse,
    DocumentParseResponse,
    CitationListResponse,
    CitationBase,
)
from app.services import DocumentParser, CitationDetector

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/documents", tags=["documents"])

# Initialize services
document_parser = DocumentParser()
citation_detector = CitationDetector()


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a document for analysis.

    Accepts PDF and DOCX files containing proposed statutory amendments.
    Returns a document ID for subsequent operations.
    """
    # Validate file type
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided"
        )

    if not document_parser.is_supported(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Supported: PDF, DOCX"
        )

    # Check file size
    max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset

    if file_size > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {settings.MAX_UPLOAD_SIZE_MB}MB"
        )

    # Create document record
    file_type = document_parser.get_file_type(file.filename)
    document = Document(
        filename=file.filename,
        file_type=file_type,
        status=DocumentStatus.UPLOADED,
    )

    db.add(document)
    await db.commit()
    await db.refresh(document)

    # Save file to disk
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)

    file_path = upload_dir / f"{document.id}.{file_type}"

    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Update document with file path
        document.file_path = str(file_path)
        await db.commit()

        logger.info(f"Document uploaded: {document.id} - {file.filename}")

        return DocumentUploadResponse(
            id=document.id,
            filename=document.filename,
            file_type=document.file_type,
            status=document.status,
            created_at=document.created_at,
        )

    except Exception as e:
        logger.error(f"Error saving file: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file"
        )


@router.post("/{document_id}/parse", response_model=DocumentParseResponse)
async def parse_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Parse a document and detect citations.

    Extracts text from the uploaded file and identifies all USC, CFR,
    and Public Law citations.
    """
    # Get document
    result = await db.execute(
        select(Document).where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    if not document.file_path or not Path(document.file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document file not found"
        )

    # Update status
    document.status = DocumentStatus.PARSING
    await db.commit()

    try:
        # Parse document
        parsed = document_parser.parse(document.file_path)
        document.raw_text = parsed.raw_text

        # Detect citations
        detected = citation_detector.detect_all(parsed.raw_text)

        # Create citation records
        citations_count = 0
        for detected_citation in detected:
            citation = Citation(
                document_id=document.id,
                citation_type=CitationType(detected_citation.citation_type),
                title=detected_citation.title,
                section=detected_citation.section,
                subsection=detected_citation.subsection,
                raw_text=detected_citation.raw_text,
                position_start=detected_citation.start_pos,
                position_end=detected_citation.end_pos,
                context_text=detected_citation.context_text,
            )
            db.add(citation)
            citations_count += 1

        document.status = DocumentStatus.PARSED
        await db.commit()

        logger.info(f"Document parsed: {document_id}, {citations_count} citations found")

        return DocumentParseResponse(
            id=document.id,
            status=document.status,
            citations_found=citations_count,
            message=f"Successfully parsed document and found {citations_count} citations"
        )

    except Exception as e:
        logger.error(f"Error parsing document {document_id}: {e}")
        document.status = DocumentStatus.FAILED
        document.error_message = str(e)
        await db.commit()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to parse document: {str(e)}"
        )


@router.get("/{document_id}/citations", response_model=CitationListResponse)
async def get_document_citations(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all citations detected in a document.
    """
    # Get document with citations
    result = await db.execute(
        select(Document)
        .options(selectinload(Document.citations))
        .where(Document.id == document_id)
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found"
        )

    citations = [
        CitationBase(
            id=c.id,
            citation_type=c.citation_type,
            title=c.title,
            section=c.section,
            subsection=c.subsection,
            raw_text=c.raw_text,
            statute_fetched=c.statute_fetched,
        )
        for c in document.citations
    ]

    return CitationListResponse(
        document_id=document.id,
        citations=citations,
        total=len(citations)
    )


@router.get("/{document_id}")
async def get_document(
    document_id: UUID,
    db: AsyncSession = Depends(get_db)
):
    """
    Get document details.
    """
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

    return {
        "id": document.id,
        "filename": document.filename,
        "file_type": document.file_type,
        "status": document.status,
        "created_at": document.created_at,
        "expires_at": document.expires_at,
        "citations_count": len(document.citations),
        "comparisons_count": len(document.comparisons),
        "error_message": document.error_message,
    }
