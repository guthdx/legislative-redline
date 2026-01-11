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
    CONTEXT_WINDOW = 500  # Default fallback
    MAX_CONTEXT_FORWARD = 3000  # Max forward scan for amendment block end

    # Patterns that mark the start of a new section/subsection
    # Note: Avoid matching amendment instructions like "(A) by striking..."
    # Section headers typically start with capital words, not action verbs like "by", "in", "on"
    SECTION_BOUNDARY_PATTERN = re.compile(
        r'\n\s*(SEC\.\s*\d+\.'  # "SEC. 101." - explicit section marker
        r'|\([a-z]\)\s+[A-Z][a-z]{2,}'  # "(a) General" - subsection with title (lowercase letter)
        r'|\[\s*Option'  # "[Option" - option markers in legislative drafts
        r'|\n\n\([a-z]\)\s+[A-Z])',  # Double newline + "(a) X" - new subsection after blank line
        re.IGNORECASE  # Only affects SEC. matching, subsection patterns use explicit case
    )

    # Amendment action words that should NOT be treated as section boundaries
    AMENDMENT_ACTION_WORDS = {'by', 'in', 'on', 'at', 'and', 'or', 'to', 'for', 'the'}

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
        """
        Get text context around a citation, intelligently finding amendment boundaries.

        For amendment context, we need to capture:
        1. The beginning of the sentence/paragraph containing the citation
        2. All amendment instructions that follow (could be a numbered list)
        3. Stop at the next major section boundary
        """
        # Find the start of the line/paragraph containing the citation
        # Look back for newline followed by section marker or start of subsection
        context_start = start

        # Look back up to 200 chars to find start of the sentence/paragraph
        lookback_start = max(0, start - 200)
        lookback_text = text[lookback_start:start]

        # Find the last newline or section marker
        last_newline = lookback_text.rfind('\n')
        if last_newline != -1:
            context_start = lookback_start + last_newline + 1
        else:
            context_start = lookback_start

        # For the end, look forward for the next section boundary
        # This captures multi-line amendment blocks
        forward_text = text[end:end + self.MAX_CONTEXT_FORWARD]

        # Look for boundary patterns
        boundary_match = self.SECTION_BOUNDARY_PATTERN.search(forward_text)

        if boundary_match:
            # Found a boundary - include text up to it
            context_end = end + boundary_match.start()
        else:
            # No boundary found - use a larger window but look for double newline
            double_newline = forward_text.find('\n\n')
            if double_newline != -1 and double_newline < 1500:
                # Check if there's more amendment text after double newline
                after_newline = forward_text[double_newline:double_newline + 100]
                if re.match(r'\s*\(\d+\)\s+', after_newline):
                    # It's a numbered list item - continue
                    second_double = forward_text.find('\n\n', double_newline + 2)
                    if second_double != -1:
                        context_end = end + second_double
                    else:
                        context_end = min(len(text), end + self.MAX_CONTEXT_FORWARD)
                else:
                    context_end = end + double_newline
            else:
                # Use extended window
                context_end = min(len(text), end + 1500)

        return text[context_start:context_end].strip()

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
