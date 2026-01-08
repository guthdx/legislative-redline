# Business logic services
from app.services.document_parser import DocumentParser, ParsedDocument, ParsedSection
from app.services.citation_detector import CitationDetector, DetectedCitation
from app.services.statute_fetcher import (
    StatuteFetcherService,
    FetchedStatute,
    GovInfoFetcher,
    ECFRFetcher,
)
from app.services.amendment_parser import (
    AmendmentParser,
    AmendmentApplier,
    ParsedAmendment,
    AmendmentParseResult,
    AmendmentType,
)
from app.services.diff_generator import (
    DiffGenerator,
    DiffResult,
    generate_redline_html,
)

__all__ = [
    "DocumentParser",
    "ParsedDocument",
    "ParsedSection",
    "CitationDetector",
    "DetectedCitation",
    "StatuteFetcherService",
    "FetchedStatute",
    "GovInfoFetcher",
    "ECFRFetcher",
    "AmendmentParser",
    "AmendmentApplier",
    "ParsedAmendment",
    "AmendmentParseResult",
    "AmendmentType",
    "DiffGenerator",
    "DiffResult",
    "generate_redline_html",
]
