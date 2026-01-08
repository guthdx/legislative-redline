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
            r'(?:by\s+)?striking\s+' + QUOTE_PATTERN + r'(?!\s+and\s+insert)',
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

        amendments = []

        # Try each pattern type
        amendments.extend(self._parse_strike_insert(text))
        amendments.extend(self._parse_insert_after(text))
        amendments.extend(self._parse_insert_before(text))
        amendments.extend(self._parse_read_as_follows(text))
        amendments.extend(self._parse_add_at_end(text))
        amendments.extend(self._parse_add_at_beginning(text))
        amendments.extend(self._parse_strike_only(text))
        amendments.extend(self._parse_redesignate(text))

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

    Usage:
        applier = AmendmentApplier()
        amended_text = applier.apply(original_text, parsed_amendment)
    """

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
        if amendment.text_to_strike in text:
            return text.replace(amendment.text_to_strike, amendment.text_to_insert, 1), True
        # Try case-insensitive match
        pattern = re.compile(re.escape(amendment.text_to_strike), re.IGNORECASE)
        if pattern.search(text):
            return pattern.sub(amendment.text_to_insert, text, count=1), True
        logger.warning(f"Could not find text to strike: '{amendment.text_to_strike[:50]}...'")
        return text, False

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
        if amendment.text_to_strike in text:
            return text.replace(amendment.text_to_strike, "", 1), True
        pattern = re.compile(re.escape(amendment.text_to_strike), re.IGNORECASE)
        if pattern.search(text):
            return pattern.sub("", text, count=1), True
        logger.warning(f"Could not find text to strike: '{amendment.text_to_strike[:50]}...'")
        return text, False
