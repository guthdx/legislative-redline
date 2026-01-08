import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, DateTime, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base


class CitationType(str, enum.Enum):
    USC = "usc"
    CFR = "cfr"
    PUBLAW = "publaw"


class Citation(Base):
    __tablename__ = "citations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)

    citation_type = Column(SQLEnum(CitationType), nullable=False)
    title = Column(Integer, nullable=True)  # e.g., 26 for "26 USC"
    section = Column(String(50), nullable=False)  # e.g., "501" or "482.12"
    subsection = Column(String(100), nullable=True)  # e.g., "(c)(3)"
    raw_text = Column(String(255), nullable=False)  # Original text found in document

    # Position in document
    position_start = Column(Integer, nullable=True)
    position_end = Column(Integer, nullable=True)

    # Context around the citation (for amendment detection)
    context_text = Column(Text, nullable=True)

    # Statute fetch status
    statute_fetched = Column(Boolean, default=False)
    statute_id = Column(UUID(as_uuid=True), ForeignKey("statutes.id"), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    document = relationship("Document", back_populates="citations")
    statute = relationship("Statute", back_populates="citations")
    comparison = relationship("Comparison", back_populates="citation", uselist=False)

    def __repr__(self):
        return f"<Citation {self.raw_text}>"

    @property
    def canonical_citation(self) -> str:
        """Return a standardized citation format."""
        if self.citation_type == CitationType.USC:
            base = f"{self.title} U.S.C. § {self.section}"
            if self.subsection:
                base += f"({self.subsection})"
            return base
        elif self.citation_type == CitationType.CFR:
            return f"{self.title} C.F.R. § {self.section}"
        elif self.citation_type == CitationType.PUBLAW:
            return f"Pub. L. {self.title}-{self.section}"
        return self.raw_text
