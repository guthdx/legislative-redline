"""
Subsection Extractor Service

Extracts specific subsections from full statute text.
Handles USC subsection notation: (a), (b)(1), (a)(1)(A)(i), etc.

USC Hierarchy (typical):
- (a), (b), (c) - subsections
- (1), (2), (3) - paragraphs within subsections
- (A), (B), (C) - subparagraphs within paragraphs
- (i), (ii), (iii) - clauses within subparagraphs
- (I), (II), (III) - subclauses within clauses
"""

import re
import logging
from dataclasses import dataclass
from typing import Optional, List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class SubsectionMatch:
    """A matched subsection in the statute text."""
    notation: str  # e.g., "(b)(1)"
    text: str  # The extracted text
    start_pos: int
    end_pos: int
    level: int  # Nesting level (1 = subsection, 2 = paragraph, etc.)


@dataclass
class ExtractionResult:
    """Result of subsection extraction."""
    success: bool
    subsection_notation: str
    extracted_text: str
    full_text: str  # Original full text
    error_message: Optional[str] = None


class SubsectionExtractor:
    """
    Extracts specific subsections from statute text.

    Usage:
        extractor = SubsectionExtractor()
        result = extractor.extract(full_text, "(b)(1)")
        if result.success:
            print(result.extracted_text)
    """

    # Patterns for different subsection levels
    # Level 1: (a), (b), (c)
    SUBSECTION_PATTERN = re.compile(
        r'\(([a-z])\)',
        re.IGNORECASE
    )

    # Level 2: (1), (2), (3)
    PARAGRAPH_PATTERN = re.compile(
        r'\((\d+)\)'
    )

    # Level 3: (A), (B), (C)
    SUBPARAGRAPH_PATTERN = re.compile(
        r'\(([A-Z])\)'
    )

    # Level 4: (i), (ii), (iii), (iv), etc.
    CLAUSE_PATTERN = re.compile(
        r'\(([ivxlcdm]+)\)',
        re.IGNORECASE
    )

    # Level 5: (I), (II), (III)
    SUBCLAUSE_PATTERN = re.compile(
        r'\(([IVXLCDM]+)\)'
    )

    # Combined pattern to find any subsection marker
    ANY_MARKER_PATTERN = re.compile(
        r'\(([a-z]|\d+|[A-Z]|[ivxlcdm]+|[IVXLCDM]+)\)',
        re.IGNORECASE
    )

    def extract(self, full_text: str, subsection: str) -> ExtractionResult:
        """
        Extract a specific subsection from the full statute text.

        Args:
            full_text: The full statute text
            subsection: Subsection notation like "(a)", "(b)(1)", "(a)(1)(A)"

        Returns:
            ExtractionResult with the extracted text
        """
        if not full_text:
            return ExtractionResult(
                success=False,
                subsection_notation=subsection,
                extracted_text="",
                full_text=full_text,
                error_message="No text provided"
            )

        if not subsection:
            return ExtractionResult(
                success=True,
                subsection_notation="",
                extracted_text=full_text,
                full_text=full_text
            )

        # Parse the subsection notation into components
        components = self._parse_subsection_notation(subsection)
        if not components:
            return ExtractionResult(
                success=False,
                subsection_notation=subsection,
                extracted_text="",
                full_text=full_text,
                error_message=f"Could not parse subsection notation: {subsection}"
            )

        logger.debug(f"Extracting subsection {subsection} with components: {components}")

        # Navigate through the text to find the target subsection
        extracted = self._extract_nested(full_text, components)

        if extracted:
            return ExtractionResult(
                success=True,
                subsection_notation=subsection,
                extracted_text=extracted,
                full_text=full_text
            )
        else:
            return ExtractionResult(
                success=False,
                subsection_notation=subsection,
                extracted_text="",
                full_text=full_text,
                error_message=f"Could not find subsection {subsection} in text"
            )

    def _parse_subsection_notation(self, notation: str) -> List[str]:
        """
        Parse subsection notation into components.

        Examples:
            "(a)" -> ["a"]
            "(b)(1)" -> ["b", "1"]
            "(a)(1)(A)(i)" -> ["a", "1", "A", "i"]
        """
        # Find all parenthetical markers
        matches = re.findall(r'\(([^)]+)\)', notation)
        return matches

    def _extract_nested(self, text: str, components: List[str]) -> Optional[str]:
        """
        Extract text by navigating through nested subsection markers.

        For each component, find the marker and extract text until the next
        marker at the same or higher level.
        """
        current_text = text
        remaining_components = list(components)

        while remaining_components:
            component = remaining_components.pop(0)
            marker = f"({component})"

            # Find the marker in current text
            marker_pos = self._find_marker(current_text, marker)
            if marker_pos == -1:
                logger.debug(f"Could not find marker {marker}")
                return None

            # Extract from marker to the end of this subsection
            start = marker_pos
            end = self._find_subsection_end(current_text, start, component)

            current_text = current_text[start:end].strip()

        return current_text

    def _find_marker(self, text: str, marker: str) -> int:
        """
        Find a subsection marker in text, handling edge cases.

        The marker should appear at the start of a subsection, typically:
        - After a newline
        - After a period and space
        - At paragraph boundaries
        """
        # Try exact match first
        pos = text.find(marker)
        if pos != -1:
            return pos

        # Try case-insensitive for letter markers
        marker_lower = marker.lower()
        text_lower = text.lower()
        pos = text_lower.find(marker_lower)
        if pos != -1:
            return pos

        return -1

    def _find_subsection_end(self, text: str, start: int, component: str) -> int:
        """
        Find where a subsection ends.

        A subsection ends when:
        - We hit the next marker at the same level
        - We hit a marker at a higher level (less nested)
        - We reach the end of the text
        """
        level = self._get_marker_level(component)
        search_start = start + len(f"({component})")

        # Find all markers after our position
        for match in self.ANY_MARKER_PATTERN.finditer(text[search_start:]):
            match_component = match.group(1)
            match_level = self._get_marker_level(match_component)

            # Stop if we hit the same level or higher
            if match_level <= level:
                # Check if it's the next marker in sequence at same level
                if match_level == level and self._is_next_in_sequence(component, match_component):
                    return search_start + match.start()
                # Higher level marker means parent section ended
                elif match_level < level:
                    return search_start + match.start()

        # No end marker found, return end of text
        return len(text)

    def _get_marker_level(self, component: str) -> int:
        """
        Determine the nesting level of a marker component.

        Level 1: a, b, c (lowercase letters)
        Level 2: 1, 2, 3 (numbers)
        Level 3: A, B, C (uppercase letters)
        Level 4: i, ii, iii (lowercase roman numerals - must be multi-char or specific)
        Level 5: I, II, III (uppercase roman numerals - must be multi-char or specific)

        Note: Single letters like 'c', 'i', 'v' are treated as level 1/3 (subsections),
        not roman numerals. Roman numerals are typically multi-character (ii, iii, iv, etc.)
        or at most single 'i' in certain contexts.
        """
        if component.isdigit():
            return 2
        elif component.islower():
            # Single lowercase letters are always subsections (level 1)
            # Multi-character sequences that look like roman numerals are level 4
            if len(component) == 1:
                return 1  # Single letter = subsection
            elif re.match(r'^[ivxlcdm]+$', component):
                return 4  # Multi-char roman numeral
            else:
                return 1
        elif component.isupper():
            # Single uppercase letters are always subparagraphs (level 3)
            # Multi-character sequences that look like roman numerals are level 5
            if len(component) == 1:
                return 3  # Single letter = subparagraph
            elif re.match(r'^[IVXLCDM]+$', component):
                return 5  # Multi-char roman numeral
            else:
                return 3
        return 1

    def _is_next_in_sequence(self, current: str, candidate: str) -> bool:
        """Check if candidate is the next marker in sequence after current."""
        if current.isdigit() and candidate.isdigit():
            return int(candidate) == int(current) + 1

        if current.isalpha() and candidate.isalpha():
            if len(current) == 1 and len(candidate) == 1:
                return ord(candidate.lower()) == ord(current.lower()) + 1

            # Handle roman numerals
            roman_order = ['i', 'ii', 'iii', 'iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x',
                          'xi', 'xii', 'xiii', 'xiv', 'xv', 'xvi', 'xvii', 'xviii', 'xix', 'xx']
            current_lower = current.lower()
            candidate_lower = candidate.lower()
            if current_lower in roman_order and candidate_lower in roman_order:
                current_idx = roman_order.index(current_lower)
                candidate_idx = roman_order.index(candidate_lower)
                return candidate_idx == current_idx + 1

        return False

    def extract_all_subsections(self, text: str) -> List[SubsectionMatch]:
        """
        Extract all top-level subsections from the text.

        Returns a list of SubsectionMatch objects for each (a), (b), (c), etc.
        """
        matches = []
        last_end = 0

        # Find all level-1 subsection markers
        for match in self.SUBSECTION_PATTERN.finditer(text):
            component = match.group(1)
            start = match.start()

            # If we have a previous match, update its end position
            if matches:
                matches[-1].end_pos = start

            end = self._find_subsection_end(text, start, component)
            matches.append(SubsectionMatch(
                notation=f"({component})",
                text=text[start:end].strip(),
                start_pos=start,
                end_pos=end,
                level=1
            ))

        return matches


def extract_subsection(full_text: str, subsection: str) -> ExtractionResult:
    """
    Convenience function to extract a subsection.

    Args:
        full_text: The full statute text
        subsection: Subsection notation like "(a)", "(b)(1)"

    Returns:
        ExtractionResult with extracted text
    """
    extractor = SubsectionExtractor()
    return extractor.extract(full_text, subsection)
