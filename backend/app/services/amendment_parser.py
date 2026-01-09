"""
Amendment Parser Service

Parses legislative amendment instructions to extract:
- What text to strike (remove)
- What text to insert (add)
- Where to make the change (position markers)

Common amendment patterns in legislative text:
- Strike and Insert: "striking 'X' and inserting 'Y'"
- Insert After: "inserting after 'X' the following: 'Y'"
- Read as Follows: "amended to read as follows:"
- Add at End: "adding at the end the following:"
- Strike Only: "by striking 'X'"

Reference: Senate Legislative Drafting Manual, House Rules (Ramseyer rule)
"""

import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class AmendmentType(str, Enum):
    """Types of amendments detected."""
    STRIKE_INSERT = "strike_insert"
    INSERT_AFTER = "insert_after"
    INSERT_BEFORE = "insert_before"
    READ_AS_FOLLOWS = "read_as_follows"
    ADD_AT_END = "add_at_end"
    ADD_AT_BEGINNING = "add_at_beginning"
    STRIKE = "strike"
    REDESIGNATE = "redesignate"
    UNKNOWN = "unknown"


@dataclass
class ParsedAmendment:
    """A parsed amendment instruction."""
    amendment_type: AmendmentType
    text_to_strike: Optional[str] = None
    text_to_insert: Optional[str] = None
    position_marker: Optional[str] = None  # For insert_after/before
    target_section: Optional[str] = None  # Section being amended
    raw_instruction: str = ""
    confidence: float = 1.0  # 0-1, how confident we are in the parse

    @property
    def is_valid(self) -> bool:
        """Check if the amendment has enough info to apply."""
        if self.amendment_type == AmendmentType.STRIKE_INSERT:
            return bool(self.text_to_strike and self.text_to_insert)
        elif self.amendment_type == AmendmentType.INSERT_AFTER:
            return bool(self.position_marker and self.text_to_insert)
        elif self.amendment_type == AmendmentType.INSERT_BEFORE:
            return bool(self.position_marker and self.text_to_insert)
        elif self.amendment_type == AmendmentType.READ_AS_FOLLOWS:
            return bool(self.text_to_insert)
        elif self.amendment_type == AmendmentType.ADD_AT_END:
            return bool(self.text_to_insert)
        elif self.amendment_type == AmendmentType.ADD_AT_BEGINNING:
            return bool(self.text_to_insert)
        elif self.amendment_type == AmendmentType.STRIKE:
            return bool(self.text_to_strike)
        return False


@dataclass
class AmendmentParseResult:
    """Result of parsing amendment text."""
    amendments: List[ParsedAmendment] = field(default_factory=list)
    unparsed_text: str = ""
    success: bool = False
    error_message: Optional[str] = None


class AmendmentParser:
    """
    Parses legislative amendment instructions from context text.

    Usage:
        parser = AmendmentParser()
        result = parser.parse(context_text)
        for amendment in result.amendments:
            print(f"Type: {amendment.amendment_type}")
            print(f"Strike: {amendment.text_to_strike}")
            print(f"Insert: {amendment.text_to_insert}")
    """

    # Quote normalization mappings (smart quotes -> straight quotes)
    QUOTE_NORMALIZATION = {
        '\u201c': '"',  # Left double quotation mark
        '\u201d': '"',  # Right double quotation mark
        '\u2018': "'",  # Left single quotation mark
        '\u2019': "'",  # Right single quotation mark
        '\u201a': "'",  # Single low-9 quotation mark
        '\u201b': "'",  # Single high-reversed-9 quotation mark
        '\u201e': '"',  # Double low-9 quotation mark
        '\u201f': '"',  # Double high-reversed-9 quotation mark
        '\u2032': "'",  # Prime
        '\u2033': '"',  # Double prime
    }

    @staticmethod
    def normalize_quotes(text: str) -> str:
        """
        Normalize smart quotes and other quote variants to standard ASCII quotes.

        This ensures consistent pattern matching regardless of the source document's
        quote style (Word, Google Docs, PDF, etc.).

        Args:
            text: The text to normalize

        Returns:
            Text with all quote variants converted to straight quotes
        """
        for smart_quote, straight_quote in AmendmentParser.QUOTE_NORMALIZATION.items():
            text = text.replace(smart_quote, straight_quote)
        return text

    # Patterns for different amendment types
    # Using non-greedy matching and flexible quote handling

    # Pattern for quoted text - handles single quotes, double quotes, and smart quotes
    QUOTE_PATTERN = r'["\u201c\u201d\u2018\u2019\']([^"\u201c\u201d\u2018\u2019\']+)["\u201c\u201d\u2018\u2019\']'

    # Alternative: text between quotes or after colon until period/semicolon
    TEXT_AFTER_COLON = r':\s*["\u201c]?([^"\u201d;.]+)["\u201d]?'

    # Strike and Insert patterns
    STRIKE_INSERT_PATTERNS = [
        # "by striking 'X' and inserting 'Y'"
        re.compile(
            r'(?:by\s+)?striking\s+' + QUOTE_PATTERN + r'\s+and\s+inserting\s+' + QUOTE_PATTERN,
            re.IGNORECASE | re.DOTALL
        ),
        # "strike 'X' and insert 'Y'"
        re.compile(
            r'strike\s+' + QUOTE_PATTERN + r'\s+and\s+insert(?:ing)?\s+' + QUOTE_PATTERN,
            re.IGNORECASE | re.DOTALL
        ),
        # "striking out 'X' and inserting in lieu thereof 'Y'"
        re.compile(
            r'striking\s+out\s+' + QUOTE_PATTERN + r'\s+and\s+inserting\s+(?:in\s+lieu\s+thereof\s+)?' + QUOTE_PATTERN,
            re.IGNORECASE | re.DOTALL
        ),
        # "by striking 'X' and inserting in place thereof 'Y'"
        re.compile(
            r'(?:by\s+)?striking\s+' + QUOTE_PATTERN + r'\s+and\s+inserting\s+in\s+place\s+thereof\s+' + QUOTE_PATTERN,
            re.IGNORECASE | re.DOTALL
        ),
        # "by striking 'X' and all that follows through the period at the end and inserting 'Y'"
        re.compile(
            r'(?:by\s+)?striking\s+' + QUOTE_PATTERN + r'\s+and\s+all\s+that\s+follows\s+through\s+the\s+period\s+at\s+the\s+end\s+and\s+inserting\s+' + QUOTE_PATTERN,
            re.IGNORECASE | re.DOTALL
        ),
        # "by striking paragraph (X) and inserting the following:"
        re.compile(
            r'(?:by\s+)?striking\s+paragraph\s*\((\d+)\)\s+and\s+inserting\s+(?:the\s+following[:\s]+)?(.+?)(?=\n\n|\Z|"\.\s*$)',
            re.IGNORECASE | re.DOTALL
        ),
    ]

    # Strike through end patterns (special case - strikes from marker through end of provision)
    STRIKE_THROUGH_END_PATTERNS = [
        # "by striking 'X' and all that follows through the period at the end and inserting 'Y'"
        re.compile(
            r'(?:by\s+)?striking\s+' + QUOTE_PATTERN + r'\s+and\s+all\s+that\s+follows\s+through\s+(?:the\s+)?(?:period|semicolon)\s+at\s+the\s+end\s+and\s+inserting\s+' + QUOTE_PATTERN,
            re.IGNORECASE | re.DOTALL
        ),
        # "by striking 'X' and all that follows through the period at the end" (no insert)
        re.compile(
            r'(?:by\s+)?striking\s+' + QUOTE_PATTERN + r'\s+and\s+all\s+that\s+follows\s+through\s+(?:the\s+)?(?:period|semicolon)\s+at\s+the\s+end(?!\s+and\s+insert)',
            re.IGNORECASE | re.DOTALL
        ),
    ]

    # Strike entire subparagraph/paragraph patterns
    STRIKE_SUBPARAGRAPH_PATTERNS = [
        # "by striking subparagraphs (B) and (C)"
        re.compile(
            r'(?:by\s+)?striking\s+subparagraphs?\s*\(([A-Z])\)\s+and\s+\(([A-Z])\)',
            re.IGNORECASE
        ),
        # "by striking subparagraph (X)"
        re.compile(
            r'(?:by\s+)?striking\s+subparagraph\s*\(([A-Z])\)(?!\s+and\s+insert)',
            re.IGNORECASE
        ),
        # "by striking paragraph (X)"
        re.compile(
            r'(?:by\s+)?striking\s+paragraph\s*\((\d+)\)(?!\s+and\s+insert)',
            re.IGNORECASE
        ),
        # "by striking subsection (x)"
        re.compile(
            r'(?:by\s+)?striking\s+subsection\s*\(([a-z])\)',
            re.IGNORECASE
        ),
    ]

    # Insert After patterns
    INSERT_AFTER_PATTERNS = [
        # "by inserting after 'X' the following: 'Y'"
        re.compile(
            r'(?:by\s+)?inserting\s+(?:immediately\s+)?after\s+' + QUOTE_PATTERN + r'\s+(?:the\s+following[:\s]+)?' + QUOTE_PATTERN,
            re.IGNORECASE | re.DOTALL
        ),
        # "inserting after 'X': 'Y'"
        re.compile(
            r'inserting\s+after\s+' + QUOTE_PATTERN + TEXT_AFTER_COLON,
            re.IGNORECASE | re.DOTALL
        ),
    ]

    # Insert Before patterns
    INSERT_BEFORE_PATTERNS = [
        # "by inserting before 'X' the following: 'Y'"
        re.compile(
            r'(?:by\s+)?inserting\s+(?:immediately\s+)?before\s+' + QUOTE_PATTERN + r'\s+(?:the\s+following[:\s]+)?' + QUOTE_PATTERN,
            re.IGNORECASE | re.DOTALL
        ),
    ]

    # Read as Follows patterns
    READ_AS_FOLLOWS_PATTERNS = [
        # "is amended to read as follows:"
        re.compile(
            r'(?:is\s+)?amended\s+to\s+read\s+as\s+follows[:\s]+(.+?)(?=\n\n|\Z)',
            re.IGNORECASE | re.DOTALL
        ),
        # "shall read as follows:"
        re.compile(
            r'shall\s+read\s+as\s+follows[:\s]+(.+?)(?=\n\n|\Z)',
            re.IGNORECASE | re.DOTALL
        ),
    ]

    # Add at End patterns
    ADD_AT_END_PATTERNS = [
        # "by adding at the end the following:"
        re.compile(
            r'(?:by\s+)?adding\s+at\s+the\s+end\s+(?:thereof\s+)?(?:the\s+following[:\s]+)?(.+?)(?=\n\n|\Z)',
            re.IGNORECASE | re.DOTALL
        ),
        # "by adding at the end:"
        re.compile(
            r'(?:by\s+)?adding\s+at\s+the\s+end' + TEXT_AFTER_COLON,
            re.IGNORECASE | re.DOTALL
        ),
    ]

    # Add at Beginning patterns
    ADD_AT_BEGINNING_PATTERNS = [
        # "by inserting at the beginning the following:"
        re.compile(
            r'(?:by\s+)?(?:inserting|adding)\s+(?:at\s+)?the\s+beginning\s+(?:thereof\s+)?(?:the\s+following[:\s]+)?(.+?)(?=\n\n|\Z)',
            re.IGNORECASE | re.DOTALL
        ),
    ]

    # Strike Only patterns
    STRIKE_PATTERNS = [
        # "by striking 'X'"
        re.compile(
            r'(?:by\s+)?striking\s+' + QUOTE_PATTERN + r'(?!\s+and\s+insert)(?!\s+each\s+place)',
            re.IGNORECASE
        ),
        # "by deleting 'X'"
        re.compile(
            r'(?:by\s+)?deleting\s+' + QUOTE_PATTERN,
            re.IGNORECASE
        ),
        # "strike out 'X'"
        re.compile(
            r'strike\s+out\s+' + QUOTE_PATTERN,
            re.IGNORECASE
        ),
        # "by striking 'X' at the end" - strikes specific text at end of provision
        re.compile(
            r'(?:by\s+)?striking\s+' + QUOTE_PATTERN + r'\s+at\s+the\s+end(?!\s+and)',
            re.IGNORECASE
        ),
    ]

    # Strike "each place it appears" patterns (global replacement)
    STRIKE_EACH_PLACE_PATTERNS = [
        # "by striking 'X' each place it appears"
        re.compile(
            r'(?:by\s+)?striking\s+' + QUOTE_PATTERN + r'\s+each\s+place\s+(?:it|the\s+term)\s+appears',
            re.IGNORECASE
        ),
        # "by striking 'X' each place it appears and inserting 'Y'"
        re.compile(
            r'(?:by\s+)?striking\s+' + QUOTE_PATTERN + r'\s+each\s+place\s+(?:it|the\s+term)\s+appears\s+and\s+inserting\s+' + QUOTE_PATTERN,
            re.IGNORECASE
        ),
    ]

    # Strike at End and Insert patterns (common in real bills)
    STRIKE_END_INSERT_PATTERNS = [
        # "by striking the period at the end and inserting '; or'"
        re.compile(
            r'(?:by\s+)?striking\s+the\s+(\w+)\s+at\s+the\s+end\s+and\s+inserting\s+' + QUOTE_PATTERN,
            re.IGNORECASE
        ),
        # "by striking 'X' at the end and inserting 'Y'"
        re.compile(
            r'(?:by\s+)?striking\s+' + QUOTE_PATTERN + r'\s+at\s+the\s+end\s+and\s+inserting\s+' + QUOTE_PATTERN,
            re.IGNORECASE
        ),
    ]

    # Subparagraph-targeted amendment patterns
    SUBPARAGRAPH_PATTERNS = [
        # "on subparagraph (D), by striking 'X' at the end"
        re.compile(
            r'(?:on|in)\s+(?:subparagraph|paragraph|clause)\s*\(([A-Za-z0-9]+)\)[,\s]+(?:by\s+)?striking\s+' + QUOTE_PATTERN + r'\s+at\s+the\s+end',
            re.IGNORECASE
        ),
        # "on subparagraph (E)(ii), by striking the period at the end and inserting '; or'" (quoted insert)
        re.compile(
            r'(?:on|in)\s+(?:subparagraph|paragraph|clause)\s*\(([A-Za-z0-9]+)\)(?:\s*\(([ivxlcdm0-9]+)\))?[,\s]+(?:by\s+)?striking\s+(?:the\s+)?(\w+)\s+at\s+the\s+end\s+and\s+inserting\s+' + QUOTE_PATTERN,
            re.IGNORECASE
        ),
        # "on subparagraph (A), by striking the semicolon at the end and inserting a period" (unquoted insert)
        re.compile(
            r'(?:on|in)\s+(?:subparagraph|paragraph|clause)\s*\(([A-Za-z0-9]+)\)(?:\s*\(([ivxlcdm0-9]+)\))?[,\s]+(?:by\s+)?striking\s+(?:the\s+)?(\w+)\s+at\s+the\s+end\s+and\s+inserting\s+(?:a\s+)?(\w+)',
            re.IGNORECASE
        ),
        # "by striking subparagraph (E) and inserting the following:"
        re.compile(
            r'(?:by\s+)?striking\s+(?:subparagraph|paragraph|clause)\s*\(([A-Za-z0-9]+)\)\s+and\s+inserting\s+(?:the\s+following[:\s]+)?(.+?)(?=\n\n|\Z|"\.|"\s*$)',
            re.IGNORECASE | re.DOTALL
        ),
    ]

    # Redesignate patterns
    REDESIGNATE_PATTERNS = [
        # "by redesignating subsection (a) as subsection (b)"
        re.compile(
            r'(?:by\s+)?redesignating\s+(\w+\s*\([^)]+\))\s+as\s+(\w+\s*\([^)]+\))',
            re.IGNORECASE
        ),
    ]

    # Section reference pattern
    SECTION_REF_PATTERN = re.compile(
        r'(?:section|subsection|paragraph|subparagraph)\s*\(?\d+\)?(?:\s*\([a-zA-Z0-9]+\))*',
        re.IGNORECASE
    )

    # Pattern to detect if text is definitional (not an actual amendment)
    DEFINITIONAL_PATTERNS = [
        re.compile(r'\(as\s+defined\s+in\s+(?:section|paragraph)', re.IGNORECASE),
        re.compile(r'has\s+the\s+meaning\s+given', re.IGNORECASE),
        re.compile(r'the\s+term\s+["\'].+?["\']\s+means', re.IGNORECASE),
        re.compile(r'for\s+purposes\s+of\s+this', re.IGNORECASE),
        re.compile(r'under\s+(?:section|paragraph|subparagraph)', re.IGNORECASE),
    ]

    # Pattern to detect actual amendment language
    AMENDMENT_INDICATOR_PATTERNS = [
        re.compile(r'is\s+amended', re.IGNORECASE),
        re.compile(r'are\s+amended', re.IGNORECASE),
        re.compile(r'is\s+hereby\s+amended', re.IGNORECASE),
        re.compile(r'shall\s+be\s+amended', re.IGNORECASE),
        re.compile(r'is\s+further\s+amended', re.IGNORECASE),  # Phase 1: further amended
        re.compile(r'are\s+further\s+amended', re.IGNORECASE),  # Phase 1: further amended (plural)
        re.compile(r'by\s+striking', re.IGNORECASE),
        re.compile(r'by\s+inserting', re.IGNORECASE),
        re.compile(r'by\s+adding', re.IGNORECASE),
        re.compile(r'by\s+redesignating', re.IGNORECASE),
    ]

    # Pattern to detect numbered amendment lists: (1) by..., (2) by...
    # Handles both "is amended—" and "is further amended—"
    NUMBERED_AMENDMENT_PATTERN = re.compile(
        r'is\s+(?:further\s+)?amended[—\-:\s]+(?:\n\s*)?(\(\d+\)[^(]+(?:\(\d+\)[^(]+)*)',
        re.IGNORECASE | re.DOTALL
    )

    def is_definitional_reference(self, text: str) -> bool:
        """
        Check if text is a definitional reference rather than an actual amendment.

        Args:
            text: Context text to analyze

        Returns:
            True if text appears to be definitional, False if it may contain amendments
        """
        # Check for definitional patterns
        for pattern in self.DEFINITIONAL_PATTERNS:
            if pattern.search(text):
                # But also check if there's amendment language
                for amend_pattern in self.AMENDMENT_INDICATOR_PATTERNS:
                    if amend_pattern.search(text):
                        return False  # Has amendment language, not just definitional
                return True
        return False

    def is_amendment_context(self, text: str) -> bool:
        """
        Check if text contains actual amendment instructions.

        Args:
            text: Context text to analyze

        Returns:
            True if text appears to contain amendment instructions
        """
        for pattern in self.AMENDMENT_INDICATOR_PATTERNS:
            if pattern.search(text):
                return True
        return False

    def parse(self, text: str) -> AmendmentParseResult:
        """
        Parse amendment instructions from text.

        Args:
            text: The context text containing amendment instructions

        Returns:
            AmendmentParseResult with parsed amendments
        """
        if not text:
            return AmendmentParseResult(
                success=False,
                error_message="No text provided"
            )

        # Phase 1: Normalize quotes before processing
        # This ensures consistent pattern matching regardless of source document
        text = self.normalize_quotes(text)

        # Check if this is just a definitional reference
        if self.is_definitional_reference(text) and not self.is_amendment_context(text):
            return AmendmentParseResult(
                success=False,
                error_message="Text appears to be a definitional reference, not an amendment"
            )

        amendments = []

        # First, try to parse numbered amendment lists (most common in real bills)
        amendments.extend(self._parse_numbered_amendments(text))

        # Try each pattern type
        amendments.extend(self._parse_strike_insert(text))
        amendments.extend(self._parse_strike_end_insert(text))
        amendments.extend(self._parse_strike_through_end(text))
        amendments.extend(self._parse_strike_subparagraphs(text))
        amendments.extend(self._parse_subparagraph_amendments(text))
        amendments.extend(self._parse_insert_after(text))
        amendments.extend(self._parse_insert_before(text))
        amendments.extend(self._parse_read_as_follows(text))
        amendments.extend(self._parse_add_at_end(text))
        amendments.extend(self._parse_add_at_beginning(text))
        amendments.extend(self._parse_strike_only(text))
        amendments.extend(self._parse_strike_each_place(text))
        amendments.extend(self._parse_redesignate(text))

        # Deduplicate amendments (some may be captured by multiple patterns)
        amendments = self._deduplicate_amendments(amendments)

        # If no patterns matched, try to detect amendment type from keywords
        if not amendments:
            amendment = self._detect_from_keywords(text)
            if amendment:
                amendments.append(amendment)

        # Extract target section references
        for amendment in amendments:
            section_match = self.SECTION_REF_PATTERN.search(text)
            if section_match:
                amendment.target_section = section_match.group(0)

        return AmendmentParseResult(
            amendments=amendments,
            unparsed_text=text if not amendments else "",
            success=len(amendments) > 0
        )

    def _deduplicate_amendments(self, amendments: List[ParsedAmendment]) -> List[ParsedAmendment]:
        """Remove duplicate amendments based on raw_instruction."""
        seen = set()
        unique = []
        for amendment in amendments:
            key = (amendment.amendment_type, amendment.text_to_strike, amendment.text_to_insert)
            if key not in seen:
                seen.add(key)
                unique.append(amendment)
        return unique

    def _parse_strike_insert(self, text: str) -> List[ParsedAmendment]:
        """Parse strike-and-insert amendments."""
        amendments = []
        for pattern in self.STRIKE_INSERT_PATTERNS:
            for match in pattern.finditer(text):
                amendments.append(ParsedAmendment(
                    amendment_type=AmendmentType.STRIKE_INSERT,
                    text_to_strike=match.group(1).strip(),
                    text_to_insert=match.group(2).strip(),
                    raw_instruction=match.group(0),
                    confidence=0.9
                ))
        return amendments

    def _parse_numbered_amendments(self, text: str) -> List[ParsedAmendment]:
        """
        Parse numbered amendment lists like:
        is amended—
        (1) on subparagraph (D), by striking "or" at the end;
        (2) on subparagraph (E)(ii), by striking the period at the end and inserting "; or"; and
        (3) by adding at the end the following: "(F) otherwise refinancing indebtedness."
        """
        amendments = []

        # Find numbered amendment blocks
        match = self.NUMBERED_AMENDMENT_PATTERN.search(text)
        if match:
            numbered_text = match.group(1)
            # Split by numbered items: (1), (2), (3), etc.
            items = re.split(r'\(\d+\)\s*', numbered_text)
            items = [item.strip() for item in items if item.strip()]

            for item in items:
                # Parse each numbered item individually
                item_amendments = self._parse_single_amendment_item(item)
                amendments.extend(item_amendments)

        return amendments

    def _parse_single_amendment_item(self, item: str) -> List[ParsedAmendment]:
        """Parse a single amendment item from a numbered list."""
        amendments = []

        # Pattern: "on subparagraph (X), by striking 'Y' at the end"
        strike_at_end_match = re.search(
            r'(?:on|in)\s+(?:subparagraph|paragraph|clause)\s*\(([A-Za-z0-9]+)\)[,\s]+(?:by\s+)?striking\s+["\']([^"\']+)["\'](?:\s+at\s+the\s+end)?',
            item, re.IGNORECASE
        )
        if strike_at_end_match:
            amendments.append(ParsedAmendment(
                amendment_type=AmendmentType.STRIKE,
                text_to_strike=strike_at_end_match.group(2),
                target_section=f"subparagraph ({strike_at_end_match.group(1)})",
                raw_instruction=item,
                confidence=0.9
            ))
            return amendments

        # Pattern: "on subparagraph (X), by striking the period at the end and inserting '; or'"
        strike_word_insert_match = re.search(
            r'(?:on|in)\s+(?:subparagraph|paragraph|clause)\s*\(([A-Za-z0-9]+)\)(?:\s*\(([ivxlcdm0-9]+)\))?[,\s]+(?:by\s+)?striking\s+(?:the\s+)?(\w+)\s+at\s+the\s+end\s+and\s+inserting\s+["\']([^"\']+)["\']',
            item, re.IGNORECASE
        )
        if strike_word_insert_match:
            subpara = strike_word_insert_match.group(1)
            clause = strike_word_insert_match.group(2)
            word_to_strike = strike_word_insert_match.group(3)
            text_to_insert = strike_word_insert_match.group(4)
            target = f"subparagraph ({subpara})" + (f"({clause})" if clause else "")

            # Map common words to actual characters
            strike_text = {"period": ".", "comma": ",", "semicolon": ";"}.get(word_to_strike.lower(), word_to_strike)

            amendments.append(ParsedAmendment(
                amendment_type=AmendmentType.STRIKE_INSERT,
                text_to_strike=strike_text,
                text_to_insert=text_to_insert,
                target_section=target,
                raw_instruction=item,
                confidence=0.9
            ))
            return amendments

        # Pattern: "by adding at the end the following: '(F) ...'""
        add_at_end_match = re.search(
            r'(?:by\s+)?adding\s+at\s+the\s+end\s+(?:the\s+following[:\s]+)?["\']?(.+?)["\']?\s*[\.;]?\s*$',
            item, re.IGNORECASE | re.DOTALL
        )
        if add_at_end_match:
            amendments.append(ParsedAmendment(
                amendment_type=AmendmentType.ADD_AT_END,
                text_to_insert=add_at_end_match.group(1).strip().strip('"\''),
                raw_instruction=item,
                confidence=0.9
            ))
            return amendments

        # Pattern: "by striking subparagraph (E) and inserting the following:"
        strike_subpara_match = re.search(
            r'(?:by\s+)?striking\s+(?:subparagraph|paragraph)\s*\(([A-Za-z0-9]+)\)\s+and\s+inserting\s+(?:the\s+following[:\s]+)?["\']?(.+?)["\']?\s*$',
            item, re.IGNORECASE | re.DOTALL
        )
        if strike_subpara_match:
            amendments.append(ParsedAmendment(
                amendment_type=AmendmentType.STRIKE_INSERT,
                text_to_strike=f"subparagraph ({strike_subpara_match.group(1)})",
                text_to_insert=strike_subpara_match.group(2).strip().strip('"\''),
                raw_instruction=item,
                confidence=0.85
            ))
            return amendments

        return amendments

    def _parse_strike_end_insert(self, text: str) -> List[ParsedAmendment]:
        """Parse strike-at-end-and-insert amendments."""
        amendments = []
        for pattern in self.STRIKE_END_INSERT_PATTERNS:
            for match in pattern.finditer(text):
                groups = match.groups()
                if len(groups) == 2:
                    # "by striking the period at the end and inserting '; or'"
                    word_to_strike = groups[0]
                    text_to_insert = groups[1]
                    # Map common words to characters
                    strike_text = {"period": ".", "comma": ",", "semicolon": ";"}.get(word_to_strike.lower(), word_to_strike)
                    amendments.append(ParsedAmendment(
                        amendment_type=AmendmentType.STRIKE_INSERT,
                        text_to_strike=strike_text,
                        text_to_insert=text_to_insert.strip(),
                        raw_instruction=match.group(0),
                        confidence=0.9
                    ))
        return amendments

    def _parse_subparagraph_amendments(self, text: str) -> List[ParsedAmendment]:
        """Parse amendments that target specific subparagraphs."""
        amendments = []
        for pattern in self.SUBPARAGRAPH_PATTERNS:
            for match in pattern.finditer(text):
                groups = match.groups()
                raw_instr = match.group(0).lower()
                if len(groups) >= 2:
                    subpara = groups[0]
                    if len(groups) == 2:
                        # Check if this is strike-and-insert or just strike
                        if 'and inserting' in raw_instr:
                            # Strike whole subparagraph and insert replacement
                            # Clean up the insert text - remove leading/trailing quotes
                            insert_text = groups[1].strip().strip('"\'""''')
                            amendments.append(ParsedAmendment(
                                amendment_type=AmendmentType.STRIKE_INSERT,
                                text_to_strike=f"subparagraph ({subpara})",
                                text_to_insert=insert_text,
                                target_section=f"subparagraph ({subpara})",
                                raw_instruction=match.group(0),
                                confidence=0.9
                            ))
                        else:
                            # Simple subparagraph strike (at end)
                            amendments.append(ParsedAmendment(
                                amendment_type=AmendmentType.STRIKE,
                                text_to_strike=groups[1],
                                target_section=f"subparagraph ({subpara})",
                                raw_instruction=match.group(0),
                                confidence=0.9
                            ))
                    elif len(groups) >= 4:
                        # Strike word and insert
                        clause = groups[1] if groups[1] else ""
                        word_to_strike = groups[2]
                        word_to_insert = groups[3]
                        # Map common word names to actual characters
                        word_map = {"period": ".", "comma": ",", "semicolon": ";", "colon": ":"}
                        strike_text = word_map.get(word_to_strike.lower(), word_to_strike)
                        insert_text = word_map.get(word_to_insert.lower(), word_to_insert)
                        target = f"subparagraph ({subpara})" + (f"({clause})" if clause else "")
                        amendments.append(ParsedAmendment(
                            amendment_type=AmendmentType.STRIKE_INSERT,
                            text_to_strike=strike_text,
                            text_to_insert=insert_text.strip(),
                            target_section=target,
                            raw_instruction=match.group(0),
                            confidence=0.9
                        ))
        return amendments

    def _parse_insert_after(self, text: str) -> List[ParsedAmendment]:
        """Parse insert-after amendments."""
        amendments = []
        for pattern in self.INSERT_AFTER_PATTERNS:
            for match in pattern.finditer(text):
                amendments.append(ParsedAmendment(
                    amendment_type=AmendmentType.INSERT_AFTER,
                    position_marker=match.group(1).strip(),
                    text_to_insert=match.group(2).strip(),
                    raw_instruction=match.group(0),
                    confidence=0.9
                ))
        return amendments

    def _parse_insert_before(self, text: str) -> List[ParsedAmendment]:
        """Parse insert-before amendments."""
        amendments = []
        for pattern in self.INSERT_BEFORE_PATTERNS:
            for match in pattern.finditer(text):
                amendments.append(ParsedAmendment(
                    amendment_type=AmendmentType.INSERT_BEFORE,
                    position_marker=match.group(1).strip(),
                    text_to_insert=match.group(2).strip(),
                    raw_instruction=match.group(0),
                    confidence=0.9
                ))
        return amendments

    def _parse_read_as_follows(self, text: str) -> List[ParsedAmendment]:
        """Parse read-as-follows amendments (full replacement)."""
        amendments = []
        for pattern in self.READ_AS_FOLLOWS_PATTERNS:
            for match in pattern.finditer(text):
                amendments.append(ParsedAmendment(
                    amendment_type=AmendmentType.READ_AS_FOLLOWS,
                    text_to_insert=match.group(1).strip(),
                    raw_instruction=match.group(0),
                    confidence=0.85  # Lower confidence - full text replacement
                ))
        return amendments

    def _parse_add_at_end(self, text: str) -> List[ParsedAmendment]:
        """Parse add-at-end amendments."""
        amendments = []
        for pattern in self.ADD_AT_END_PATTERNS:
            for match in pattern.finditer(text):
                amendments.append(ParsedAmendment(
                    amendment_type=AmendmentType.ADD_AT_END,
                    text_to_insert=match.group(1).strip(),
                    raw_instruction=match.group(0),
                    confidence=0.9
                ))
        return amendments

    def _parse_add_at_beginning(self, text: str) -> List[ParsedAmendment]:
        """Parse add-at-beginning amendments."""
        amendments = []
        for pattern in self.ADD_AT_BEGINNING_PATTERNS:
            for match in pattern.finditer(text):
                amendments.append(ParsedAmendment(
                    amendment_type=AmendmentType.ADD_AT_BEGINNING,
                    text_to_insert=match.group(1).strip(),
                    raw_instruction=match.group(0),
                    confidence=0.9
                ))
        return amendments

    def _parse_strike_only(self, text: str) -> List[ParsedAmendment]:
        """Parse strike-only amendments (deletion without insertion)."""
        amendments = []
        for pattern in self.STRIKE_PATTERNS:
            for match in pattern.finditer(text):
                amendments.append(ParsedAmendment(
                    amendment_type=AmendmentType.STRIKE,
                    text_to_strike=match.group(1).strip(),
                    raw_instruction=match.group(0),
                    confidence=0.9
                ))
        return amendments

    def _parse_strike_each_place(self, text: str) -> List[ParsedAmendment]:
        """Parse 'strike X each place it appears' amendments (global replacement)."""
        amendments = []
        for pattern in self.STRIKE_EACH_PLACE_PATTERNS:
            for match in pattern.finditer(text):
                groups = match.groups()
                if len(groups) == 2:
                    # Strike and replace each place
                    amendments.append(ParsedAmendment(
                        amendment_type=AmendmentType.STRIKE_INSERT,
                        text_to_strike=groups[0].strip() + " [each place it appears]",
                        text_to_insert=groups[1].strip(),
                        raw_instruction=match.group(0),
                        confidence=0.9
                    ))
                elif len(groups) == 1:
                    # Strike only each place
                    amendments.append(ParsedAmendment(
                        amendment_type=AmendmentType.STRIKE,
                        text_to_strike=groups[0].strip() + " [each place it appears]",
                        raw_instruction=match.group(0),
                        confidence=0.9
                    ))
        return amendments

    def _parse_strike_through_end(self, text: str) -> List[ParsedAmendment]:
        """Parse 'strike X and all that follows through the period at the end' amendments."""
        amendments = []
        for pattern in self.STRIKE_THROUGH_END_PATTERNS:
            for match in pattern.finditer(text):
                groups = match.groups()
                if len(groups) == 2:
                    # Has both strike marker and insert text
                    amendments.append(ParsedAmendment(
                        amendment_type=AmendmentType.STRIKE_INSERT,
                        text_to_strike=groups[0].strip() + " [and all that follows through end]",
                        text_to_insert=groups[1].strip(),
                        raw_instruction=match.group(0),
                        confidence=0.85
                    ))
                elif len(groups) == 1:
                    # Strike only, no insert
                    amendments.append(ParsedAmendment(
                        amendment_type=AmendmentType.STRIKE,
                        text_to_strike=groups[0].strip() + " [and all that follows through end]",
                        raw_instruction=match.group(0),
                        confidence=0.85
                    ))
        return amendments

    def _parse_strike_subparagraphs(self, text: str) -> List[ParsedAmendment]:
        """Parse amendments that strike entire subparagraphs, paragraphs, or subsections."""
        amendments = []
        for pattern in self.STRIKE_SUBPARAGRAPH_PATTERNS:
            for match in pattern.finditer(text):
                groups = match.groups()
                if len(groups) == 2:
                    # Striking multiple: "subparagraphs (B) and (C)"
                    amendments.append(ParsedAmendment(
                        amendment_type=AmendmentType.STRIKE,
                        text_to_strike=f"subparagraphs ({groups[0]}) and ({groups[1]})",
                        raw_instruction=match.group(0),
                        confidence=0.9
                    ))
                elif len(groups) == 1:
                    # Determine what type we're striking based on the raw match
                    raw = match.group(0).lower()
                    if 'subsection' in raw:
                        target = f"subsection ({groups[0]})"
                    elif 'paragraph' in raw and 'sub' not in raw:
                        target = f"paragraph ({groups[0]})"
                    else:
                        target = f"subparagraph ({groups[0]})"
                    amendments.append(ParsedAmendment(
                        amendment_type=AmendmentType.STRIKE,
                        text_to_strike=target,
                        raw_instruction=match.group(0),
                        confidence=0.9
                    ))
        return amendments

    def _parse_redesignate(self, text: str) -> List[ParsedAmendment]:
        """Parse redesignation amendments."""
        amendments = []
        for pattern in self.REDESIGNATE_PATTERNS:
            for match in pattern.finditer(text):
                amendments.append(ParsedAmendment(
                    amendment_type=AmendmentType.REDESIGNATE,
                    text_to_strike=match.group(1).strip(),
                    text_to_insert=match.group(2).strip(),
                    raw_instruction=match.group(0),
                    confidence=0.85
                ))
        return amendments

    def _detect_from_keywords(self, text: str) -> Optional[ParsedAmendment]:
        """Detect amendment type from keywords when patterns don't match."""
        text_lower = text.lower()

        if "striking" in text_lower and "inserting" in text_lower:
            return ParsedAmendment(
                amendment_type=AmendmentType.STRIKE_INSERT,
                raw_instruction=text[:200],
                confidence=0.5
            )
        elif "inserting after" in text_lower:
            return ParsedAmendment(
                amendment_type=AmendmentType.INSERT_AFTER,
                raw_instruction=text[:200],
                confidence=0.5
            )
        elif "read as follows" in text_lower:
            return ParsedAmendment(
                amendment_type=AmendmentType.READ_AS_FOLLOWS,
                raw_instruction=text[:200],
                confidence=0.5
            )
        elif "adding at the end" in text_lower:
            return ParsedAmendment(
                amendment_type=AmendmentType.ADD_AT_END,
                raw_instruction=text[:200],
                confidence=0.5
            )
        elif "striking" in text_lower or "deleting" in text_lower:
            return ParsedAmendment(
                amendment_type=AmendmentType.STRIKE,
                raw_instruction=text[:200],
                confidence=0.5
            )

        return None


class AmendmentApplier:
    """
    Applies parsed amendments to original statute text.

    Enhanced to handle:
    - Structural references (subparagraph (A), paragraph (1), subsection (a))
    - "All that follows through the period at the end" patterns
    - "Each place it appears" global replacements

    Usage:
        applier = AmendmentApplier()
        amended_text = applier.apply(original_text, parsed_amendment)
    """

    # Patterns to find structural elements in statute text
    # Subsection pattern: (a), (b), etc. at start of line or after newline
    SUBSECTION_PATTERN = re.compile(r'\n?\s*\(([a-z])\)\s+', re.IGNORECASE)
    # Paragraph pattern: (1), (2), etc.
    PARAGRAPH_PATTERN = re.compile(r'\n?\s*\((\d+)\)\s+')
    # Subparagraph pattern: (A), (B), etc.
    SUBPARAGRAPH_PATTERN = re.compile(r'\n?\s*\(([A-Z])\)\s+')
    # Clause pattern: (i), (ii), (iii), etc.
    CLAUSE_PATTERN = re.compile(r'\n?\s*\(([ivxlcdm]+)\)\s+', re.IGNORECASE)

    def apply(self, original_text: str, amendment: ParsedAmendment) -> Tuple[str, bool]:
        """
        Apply an amendment to the original text.

        Args:
            original_text: The original statute text
            amendment: The parsed amendment to apply

        Returns:
            Tuple of (amended_text, success)
        """
        if not amendment.is_valid:
            logger.warning(f"Cannot apply invalid amendment: {amendment.amendment_type}")
            return original_text, False

        try:
            if amendment.amendment_type == AmendmentType.STRIKE_INSERT:
                return self._apply_strike_insert(original_text, amendment)
            elif amendment.amendment_type == AmendmentType.INSERT_AFTER:
                return self._apply_insert_after(original_text, amendment)
            elif amendment.amendment_type == AmendmentType.INSERT_BEFORE:
                return self._apply_insert_before(original_text, amendment)
            elif amendment.amendment_type == AmendmentType.READ_AS_FOLLOWS:
                return self._apply_read_as_follows(original_text, amendment)
            elif amendment.amendment_type == AmendmentType.ADD_AT_END:
                return self._apply_add_at_end(original_text, amendment)
            elif amendment.amendment_type == AmendmentType.ADD_AT_BEGINNING:
                return self._apply_add_at_beginning(original_text, amendment)
            elif amendment.amendment_type == AmendmentType.STRIKE:
                return self._apply_strike(original_text, amendment)
            else:
                logger.warning(f"Unsupported amendment type: {amendment.amendment_type}")
                return original_text, False
        except Exception as e:
            logger.error(f"Error applying amendment: {e}")
            return original_text, False

    def _apply_strike_insert(self, text: str, amendment: ParsedAmendment) -> Tuple[str, bool]:
        """Replace struck text with inserted text."""
        strike_text = amendment.text_to_strike
        insert_text = amendment.text_to_insert

        # Check for special markers
        is_all_that_follows = "[and all that follows through end]" in strike_text
        is_each_place = "[each place it appears]" in strike_text
        is_structural = strike_text.startswith(("subparagraph (", "paragraph (", "subsection ("))

        # Handle "each place it appears" - global replacement
        if is_each_place:
            actual_text = strike_text.replace(" [each place it appears]", "")
            if actual_text in text:
                return text.replace(actual_text, insert_text), True
            pattern = re.compile(re.escape(actual_text), re.IGNORECASE)
            if pattern.search(text):
                return pattern.sub(insert_text, text), True
            logger.warning(f"Could not find text to strike: '{actual_text[:50]}...'")
            return text, False

        # Handle "and all that follows through the period at the end"
        if is_all_that_follows:
            actual_text = strike_text.replace(" [and all that follows through end]", "")
            return self._apply_strike_through_end(text, actual_text, insert_text)

        # Handle structural references (subparagraph (E), etc.)
        if is_structural:
            return self._apply_structural_strike_insert(text, strike_text, insert_text)

        # Standard text replacement
        if strike_text in text:
            return text.replace(strike_text, insert_text, 1), True

        # Try case-insensitive match
        pattern = re.compile(re.escape(strike_text), re.IGNORECASE)
        if pattern.search(text):
            return pattern.sub(insert_text, text, count=1), True

        logger.warning(f"Could not find text to strike: '{strike_text[:50]}...'")
        return text, False

    def _apply_strike_through_end(self, text: str, marker_text: str, insert_text: str) -> Tuple[str, bool]:
        """
        Handle "strike X and all that follows through the period at the end".

        Finds the marker text and deletes from there to the next period (end of provision).
        """
        # Find the marker text
        marker_pos = text.find(marker_text)
        if marker_pos == -1:
            # Try case-insensitive
            text_lower = text.lower()
            marker_lower = marker_text.lower()
            marker_pos = text_lower.find(marker_lower)

        if marker_pos == -1:
            logger.warning(f"Could not find marker text: '{marker_text[:50]}...'")
            return text, False

        # Find the end - look for period followed by newline or end of text
        # Also look for the typical end of a statutory provision
        end_patterns = [
            r'\.\s*\n',           # Period followed by newline
            r'\.\s*$',            # Period at end of text
            r'\.\s*\([a-z]\)',    # Period followed by next subsection
            r'\.\s*\(\d+\)',      # Period followed by next paragraph
        ]

        remaining_text = text[marker_pos:]
        end_pos = None

        for pattern in end_patterns:
            match = re.search(pattern, remaining_text)
            if match:
                # Include the period in what we're striking
                end_pos = marker_pos + match.start() + 1  # +1 to include the period
                break

        if end_pos is None:
            # Fallback: find the last period in the text
            last_period = text.rfind('.')
            if last_period > marker_pos:
                end_pos = last_period + 1
            else:
                logger.warning("Could not find end of provision")
                return text, False

        # Construct the amended text
        before_marker = text[:marker_pos]
        after_end = text[end_pos:]

        # Clean up: ensure proper spacing
        amended = before_marker.rstrip() + " " + insert_text + after_end.lstrip()
        return amended, True

    def _apply_structural_strike_insert(self, text: str, structural_ref: str, insert_text: str) -> Tuple[str, bool]:
        """
        Handle striking a structural element (subparagraph, paragraph, subsection).

        Finds the content of the referenced element and replaces it.
        """
        # Parse the structural reference
        struct_match = re.match(r'(subparagraph|paragraph|subsection)\s*\(([A-Za-z0-9]+)\)', structural_ref, re.IGNORECASE)
        if not struct_match:
            logger.warning(f"Could not parse structural reference: {structural_ref}")
            return text, False

        struct_type = struct_match.group(1).lower()
        struct_id = struct_match.group(2)

        # Find the element in the text
        element_content = self._find_structural_element(text, struct_type, struct_id)
        if element_content is None:
            logger.warning(f"Could not find {structural_ref} in text")
            return text, False

        start_pos, end_pos, content = element_content

        # Replace the content
        before = text[:start_pos]
        after = text[end_pos:]

        # Format the insert text with proper structure
        formatted_insert = f"({struct_id}) {insert_text}"
        if struct_type == "subparagraph":
            formatted_insert = f"({struct_id}) {insert_text}"

        amended = before + formatted_insert + after
        return amended, True

    def _find_structural_element(self, text: str, struct_type: str, struct_id: str) -> Optional[Tuple[int, int, str]]:
        """
        Find a structural element in the text.

        Returns: (start_position, end_position, content) or None if not found
        """
        # Build pattern based on structure type
        if struct_type == "subsection":
            pattern = re.compile(rf'\(({struct_id})\)\s+(.+?)(?=\n\s*\([a-z]\)|\Z)', re.IGNORECASE | re.DOTALL)
        elif struct_type == "paragraph":
            pattern = re.compile(rf'\(({struct_id})\)\s+(.+?)(?=\n\s*\(\d+\)|\n\s*\([a-z]\)|\Z)', re.DOTALL)
        elif struct_type == "subparagraph":
            pattern = re.compile(rf'\(({struct_id})\)\s+(.+?)(?=\n\s*\([A-Z]\)|\n\s*\(\d+\)|\n\s*\([a-z]\)|\Z)', re.DOTALL)
        else:
            return None

        match = pattern.search(text)
        if match:
            return (match.start(), match.end(), match.group(2).strip())

        # Fallback: try simpler patterns for formatted statute text
        # Look for patterns like "(E) text..." on a line
        simple_pattern = re.compile(rf'\(({struct_id})\)\s*([^\n]+)', re.IGNORECASE)
        match = simple_pattern.search(text)
        if match:
            return (match.start(), match.end(), match.group(2).strip())

        return None

    def _apply_insert_after(self, text: str, amendment: ParsedAmendment) -> Tuple[str, bool]:
        """Insert text after the position marker."""
        insert_text = " " + amendment.text_to_insert if not amendment.text_to_insert.startswith(" ") else amendment.text_to_insert
        if amendment.position_marker in text:
            return text.replace(
                amendment.position_marker,
                amendment.position_marker + insert_text,
                1
            ), True
        # Try case-insensitive
        pattern = re.compile(re.escape(amendment.position_marker), re.IGNORECASE)
        match = pattern.search(text)
        if match:
            pos = match.end()
            return text[:pos] + insert_text + text[pos:], True
        logger.warning(f"Could not find position marker: '{amendment.position_marker}'")
        return text, False

    def _apply_insert_before(self, text: str, amendment: ParsedAmendment) -> Tuple[str, bool]:
        """Insert text before the position marker."""
        insert_text = amendment.text_to_insert + " " if not amendment.text_to_insert.endswith(" ") else amendment.text_to_insert
        if amendment.position_marker in text:
            return text.replace(
                amendment.position_marker,
                insert_text + amendment.position_marker,
                1
            ), True
        pattern = re.compile(re.escape(amendment.position_marker), re.IGNORECASE)
        match = pattern.search(text)
        if match:
            pos = match.start()
            return text[:pos] + insert_text + text[pos:], True
        logger.warning(f"Could not find position marker: '{amendment.position_marker}'")
        return text, False

    def _apply_read_as_follows(self, text: str, amendment: ParsedAmendment) -> Tuple[str, bool]:
        """Replace entire text (full rewrite)."""
        # For read-as-follows, we replace the entire text
        return amendment.text_to_insert, True

    def _apply_add_at_end(self, text: str, amendment: ParsedAmendment) -> Tuple[str, bool]:
        """Add text at the end."""
        return text.rstrip() + "\n\n" + amendment.text_to_insert, True

    def _apply_add_at_beginning(self, text: str, amendment: ParsedAmendment) -> Tuple[str, bool]:
        """Add text at the beginning."""
        return amendment.text_to_insert + "\n\n" + text.lstrip(), True

    def _apply_strike(self, text: str, amendment: ParsedAmendment) -> Tuple[str, bool]:
        """Remove struck text."""
        strike_text = amendment.text_to_strike

        # Check for special markers
        is_each_place = "[each place it appears]" in strike_text
        is_structural = strike_text.startswith(("subparagraph", "paragraph", "subsection"))

        # Handle "each place it appears" - global removal
        if is_each_place:
            actual_text = strike_text.replace(" [each place it appears]", "")
            if actual_text in text:
                return text.replace(actual_text, ""), True
            pattern = re.compile(re.escape(actual_text), re.IGNORECASE)
            if pattern.search(text):
                return pattern.sub("", text), True
            logger.warning(f"Could not find text to strike: '{actual_text[:50]}...'")
            return text, False

        # Handle structural references (strike subparagraph (E), etc.)
        if is_structural:
            return self._apply_structural_strike(text, strike_text)

        # Standard text removal
        if strike_text in text:
            return text.replace(strike_text, "", 1), True
        pattern = re.compile(re.escape(strike_text), re.IGNORECASE)
        if pattern.search(text):
            return pattern.sub("", text, count=1), True
        logger.warning(f"Could not find text to strike: '{strike_text[:50]}...'")
        return text, False

    def _apply_structural_strike(self, text: str, structural_ref: str) -> Tuple[str, bool]:
        """
        Handle striking a structural element entirely.

        For "by striking subparagraphs (B) and (C)" - removes both elements.
        """
        # Check for multiple elements: "subparagraphs (B) and (C)"
        multi_match = re.match(r'subparagraphs?\s*\(([A-Z])\)\s+and\s+\(([A-Z])\)', structural_ref, re.IGNORECASE)
        if multi_match:
            # Strike multiple subparagraphs
            id1, id2 = multi_match.group(1), multi_match.group(2)
            result_text = text
            success = False

            for struct_id in [id1, id2]:
                element = self._find_structural_element(result_text, "subparagraph", struct_id)
                if element:
                    start, end, _ = element
                    result_text = result_text[:start] + result_text[end:]
                    success = True

            if success:
                return result_text, True
            logger.warning(f"Could not find subparagraphs ({id1}) and ({id2})")
            return text, False

        # Single structural element
        struct_match = re.match(r'(subparagraph|paragraph|subsection)\s*\(([A-Za-z0-9]+)\)', structural_ref, re.IGNORECASE)
        if struct_match:
            struct_type = struct_match.group(1).lower()
            struct_id = struct_match.group(2)

            element = self._find_structural_element(text, struct_type, struct_id)
            if element:
                start, end, _ = element
                return text[:start] + text[end:], True

            logger.warning(f"Could not find {structural_ref}")
            return text, False

        logger.warning(f"Could not parse structural reference: {structural_ref}")
        return text, False
