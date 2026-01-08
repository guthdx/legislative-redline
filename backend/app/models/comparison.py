import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base


class AmendmentType(str, enum.Enum):
    STRIKE_INSERT = "strike_insert"
    INSERT_AFTER = "insert_after"
    READ_AS_FOLLOWS = "read_as_follows"
    ADD_AT_END = "add_at_end"
    STRIKE = "strike"
    UNKNOWN = "unknown"


class Comparison(Base):
    __tablename__ = "comparisons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    citation_id = Column(UUID(as_uuid=True), ForeignKey("citations.id"), nullable=True)

    # Citation text for display
    citation_text = Column(String(255), nullable=True)

    # Amendment details
    amendment_type = Column(SQLEnum(AmendmentType, values_callable=lambda x: [e.value for e in x]), nullable=True)
    amendment_instruction = Column(Text, nullable=True)  # Raw amendment language

    # Text comparison
    original_text = Column(Text, nullable=True)
    amended_text = Column(Text, nullable=True)

    # Generated diff
    diff_html = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="comparisons")
    citation = relationship("Citation", back_populates="comparison")

    def __repr__(self):
        return f"<Comparison {self.citation_text} ({self.amendment_type})>"
