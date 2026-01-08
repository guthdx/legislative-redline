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
        # "by striking 'X' at the end" - strikes specific text at end of provision
        re.compile(
            r'(?:by\s+)?striking\s+' + QUOTE_PATTERN + r'\s+at\s+the\s+end(?!\s+and)',
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
        # "on subparagraph (E)(ii), by striking the period at the end and inserting '; or'"
        re.compile(
            r'(?:on|in)\s+(?:subparagraph|paragraph|clause)\s*\(([A-Za-z0-9]+)\)(?:\s*\(([ivxlcdm0-9]+)\))?[,\s]+(?:by\s+)?striking\s+(?:the\s+)?(\w+)\s+at\s+the\s+end\s+and\s+inserting\s+' + QUOTE_PATTERN,
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
        re.compile(r'by\s+striking', re.IGNORECASE),
        re.compile(r'by\s+inserting', re.IGNORECASE),
        re.compile(r'by\s+adding', re.IGNORECASE),
        re.compile(r'by\s+redesignating', re.IGNORECASE),
    ]

    # Pattern to detect numbered amendment lists: (1) by..., (2) by...
    NUMBERED_AMENDMENT_PATTERN = re.compile(
        r'is\s+amended[—\-:\s]+(?:\n\s*)?(\(\d+\)[^(]+(?:\(\d+\)[^(]+)*)',
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
        amendments.extend(self._parse_subparagraph_amendments(text))
        amendments.extend(self._parse_insert_after(text))
        amendments.extend(self._parse_insert_before(text))
        amendments.extend(self._parse_read_as_follows(text))
        amendments.extend(self._parse_add_at_end(text))
        amendments.extend(self._parse_add_at_beginning(text))
        amendments.extend(self._parse_strike_only(text))
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
                if len(groups) >= 2:
                    subpara = groups[0]
                    if len(groups) == 2:
                        # Simple subparagraph strike
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
                        text_to_insert = groups[3]
                        strike_text = {"period": ".", "comma": ",", "semicolon": ";"}.get(word_to_strike.lower(), word_to_strike)
                        target = f"subparagraph ({subpara})" + (f"({clause})" if clause else "")
                        amendments.append(ParsedAmendment(
                            amendment_type=AmendmentType.STRIKE_INSERT,
                            text_to_strike=strike_text,
                            text_to_insert=text_to_insert.strip(),
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
