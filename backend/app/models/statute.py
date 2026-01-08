import uuid
from datetime import datetime, timedelta
from sqlalchemy import Column, String, Integer, Text, DateTime, UniqueConstraint, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import enum

from app.db.session import Base


class StatuteSource(str, enum.Enum):
    GOVINFO = "govinfo"
    ECFR = "ecfr"
    MANUAL = "manual"


class Statute(Base):
    __tablename__ = "statutes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Citation identification
    citation_type = Column(String(10), nullable=False)  # usc, cfr
    title = Column(Integer, nullable=False)
    section = Column(String(50), nullable=False)

    # Content
    full_text = Column(Text, nullable=False)
    heading = Column(String(500), nullable=True)  # Section heading/title

    # Source metadata
    source = Column(SQLEnum(StatuteSource), nullable=False)
    source_url = Column(String(500), nullable=True)
    effective_date = Column(DateTime, nullable=True)

    # Cache management
    fetched_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(
        DateTime,
        default=lambda: datetime.utcnow() + timedelta(days=7)
    )

    # Relationships
    citations = relationship("Citation", back_populates="statute")

    # Unique constraint on citation type + title + section
    __table_args__ = (
        UniqueConstraint('citation_type', 'title', 'section', name='uq_statute_citation'),
    )

    def __repr__(self):
        return f"<Statute {self.citation_type} {self.title} § {self.section}>"

    @property
    def is_expired(self) -> bool:
        """Check if the cached statute has expired."""
        return datetime.utcnow() > self.expires_at
