"""
Citation Detector Service

Detects USC, CFR, and Public Law citations in text using regex patterns.
Patterns are designed to handle common variations in legal citation formats.
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Optional, Literal

logger = logging.getLogger(__name__)


@dataclass
class DetectedCitation:
    """A citation detected in text."""
    citation_type: Literal["usc", "cfr", "publaw"]
    title: Optional[int]
    section: str
    subsection: Optional[str]
    raw_text: str
    start_pos: int
    end_pos: int
    context_text: Optional[str] = None  # Text around the citation


class CitationDetector:
    """
    Detects legal citations (USC, CFR, Public Law) in text.

    Citation formats supported:
    - USC: "26 U.S.C. § 501(c)(3)", "26 USC 501", "Title 26, Section 501"
    - CFR: "42 C.F.R. § 482.12", "42 CFR 482.12"
    - Public Law: "Pub. L. 117-169", "Public Law 117-169"

    Usage:
        detector = CitationDetector()
        citations = detector.detect_all("The amendment to 26 U.S.C. § 501...")
    """

    # USC patterns - multiple variations
    USC_PATTERNS = [
        # "26 U.S.C. § 501(c)(3)" - standard format
        re.compile(
            r'\b(\d{1,2})\s*U\.?\s*S\.?\s*C\.?\s*§?\s*(\d+[a-z]?)(?:\s*\(([^)]+(?:\)\s*\([^)]+)*)\))?',
            re.IGNORECASE
        ),
        # "Title 26, Section 501" or "Title 26 Section 501"
        re.compile(
            r'Title\s+(\d{1,2}),?\s*(?:Section|Sec\.?)\s*(\d+[a-z]?)(?:\s*\(([^)]+)\))?',
            re.IGNORECASE
        ),
        # "section 501 of title 26" (reversed order)
        re.compile(
            r'[Ss]ection\s+(\d+[a-z]?)\s+of\s+[Tt]itle\s+(\d{1,2})',
            re.IGNORECASE
        ),
    ]

    # CFR patterns
    CFR_PATTERNS = [
        # "42 C.F.R. § 482.12" or "42 CFR 482.12"
        re.compile(
            r'\b(\d{1,2})\s*C\.?\s*F\.?\s*R\.?\s*§?\s*([\d]+(?:\.[\d]+)?)',
            re.IGNORECASE
        ),
    ]

    # Public Law patterns
    PUBLAW_PATTERNS = [
        # "Pub. L. 117-169" or "Public Law 117-169"
        re.compile(
            r'Pub(?:lic)?\.?\s*L(?:aw)?\.?\s*(\d+)[–-](\d+)',
            re.IGNORECASE
        ),
    ]

    # Context window size (characters before/after citation)
    CONTEXT_WINDOW = 500

    def detect_all(self, text: str) -> List[DetectedCitation]:
        """
        Detect all citations in the given text.

        Args:
            text: The text to search for citations

        Returns:
            List of DetectedCitation objects, sorted by position
        """
        citations: List[DetectedCitation] = []

        # Detect USC citations
        citations.extend(self._detect_usc(text))

        # Detect CFR citations
        citations.extend(self._detect_cfr(text))

        # Detect Public Law citations
        citations.extend(self._detect_publaw(text))

        # Remove duplicates (same citation at same position)
        citations = self._deduplicate(citations)

        # Sort by position
        citations.sort(key=lambda c: c.start_pos)

        logger.info(f"Detected {len(citations)} citations in text")

        return citations

    def _detect_usc(self, text: str) -> List[DetectedCitation]:
        """Detect USC citations."""
        citations = []

        for pattern in self.USC_PATTERNS:
            for match in pattern.finditer(text):
                groups = match.groups()

                # Handle reversed pattern (section X of title Y)
                if "of" in pattern.pattern.lower():
                    section = groups[0]
                    title = int(groups[1])
                    subsection = None
                else:
                    title = int(groups[0])
                    section = groups[1]
                    subsection = groups[2] if len(groups) > 2 else None

                # Clean up subsection (remove outer parens if present)
                if subsection:
                    subsection = subsection.strip("()")

                citations.append(DetectedCitation(
                    citation_type="usc",
                    title=title,
                    section=section,
                    subsection=subsection,
                    raw_text=match.group(0),
                    start_pos=match.start(),
                    end_pos=match.end(),
                    context_text=self._get_context(text, match.start(), match.end())
                ))

        return citations

    def _detect_cfr(self, text: str) -> List[DetectedCitation]:
        """Detect CFR citations."""
        citations = []

        for pattern in self.CFR_PATTERNS:
            for match in pattern.finditer(text):
                title = int(match.group(1))
                section = match.group(2)

                citations.append(DetectedCitation(
                    citation_type="cfr",
                    title=title,
                    section=section,
                    subsection=None,
                    raw_text=match.group(0),
                    start_pos=match.start(),
                    end_pos=match.end(),
                    context_text=self._get_context(text, match.start(), match.end())
                ))

        return citations

    def _detect_publaw(self, text: str) -> List[DetectedCitation]:
        """Detect Public Law citations."""
        citations = []

        for pattern in self.PUBLAW_PATTERNS:
            for match in pattern.finditer(text):
                congress = int(match.group(1))
                law_number = match.group(2)

                citations.append(DetectedCitation(
                    citation_type="publaw",
                    title=congress,
                    section=law_number,
                    subsection=None,
                    raw_text=match.group(0),
                    start_pos=match.start(),
                    end_pos=match.end(),
                    context_text=self._get_context(text, match.start(), match.end())
                ))

        return citations

    def _get_context(self, text: str, start: int, end: int) -> str:
        """Get text context around a citation."""
        context_start = max(0, start - self.CONTEXT_WINDOW)
        context_end = min(len(text), end + self.CONTEXT_WINDOW)
        return text[context_start:context_end]

    def _deduplicate(self, citations: List[DetectedCitation]) -> List[DetectedCitation]:
        """Remove duplicate citations (same type, title, section at overlapping positions)."""
        if not citations:
            return citations

        # Sort by position first
        citations.sort(key=lambda c: c.start_pos)

        unique = []
        seen_keys = set()

        for citation in citations:
            # Create a key based on citation identity
            key = (citation.citation_type, citation.title, citation.section)

            # Check for overlapping position with same key
            is_duplicate = False
            for existing in unique:
                existing_key = (existing.citation_type, existing.title, existing.section)
                if key == existing_key:
                    # Check if positions overlap
                    if (citation.start_pos <= existing.end_pos and
                        citation.end_pos >= existing.start_pos):
                        is_duplicate = True
                        break

            if not is_duplicate:
                unique.append(citation)

        return unique

    @staticmethod
    def format_citation(citation: DetectedCitation) -> str:
        """Format a citation in canonical form."""
        if citation.citation_type == "usc":
            base = f"{citation.title} U.S.C. § {citation.section}"
            if citation.subsection:
                base += f"({citation.subsection})"
            return base
        elif citation.citation_type == "cfr":
            return f"{citation.title} C.F.R. § {citation.section}"
        elif citation.citation_type == "publaw":
            return f"Pub. L. {citation.title}-{citation.section}"
        return citation.raw_text
