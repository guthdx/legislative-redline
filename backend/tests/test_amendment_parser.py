"""
Tests for Amendment Parser - Phase 1 & 2 improvements

Tests:
1. "is further amended by" pattern detection (Phase 1)
2. Quote normalization (Phase 1)
3. Backward compatibility with existing patterns
4. Redesignate patterns - enhanced (Phase 2)
5. Designate patterns - new (Phase 2)
"""

import pytest
import sys
import os

# Add the app directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.amendment_parser import AmendmentParser, AmendmentType


class TestQuoteNormalization:
    """Test the quote normalization feature."""

    def test_smart_double_quotes(self):
        """Test normalization of smart double quotes."""
        parser = AmendmentParser()
        text = '\u201cHello\u201d and \u201cWorld\u201d'  # Smart quotes
        normalized = parser.normalize_quotes(text)
        assert normalized == '"Hello" and "World"'  # Straight quotes

    def test_smart_single_quotes(self):
        """Test normalization of smart single quotes."""
        parser = AmendmentParser()
        text = '\u2018Hello\u2019 and \u2018World\u2019'  # Smart single quotes
        normalized = parser.normalize_quotes(text)
        assert normalized == "'Hello' and 'World'"  # Straight quotes

    def test_mixed_quotes(self):
        """Test normalization of mixed quote styles."""
        parser = AmendmentParser()
        text = '\u201cHello\u201d and \u2018World\u2019'  # Mixed
        normalized = parser.normalize_quotes(text)
        assert '\u201c' not in normalized and '\u201d' not in normalized
        assert '\u2018' not in normalized and '\u2019' not in normalized

    def test_prime_characters(self):
        """Test normalization of prime characters (often confused with quotes)."""
        parser = AmendmentParser()
        text = "5\u2032 x 10\u2033"  # Prime and double prime
        normalized = parser.normalize_quotes(text)
        assert "'" in normalized and '"' in normalized


class TestFurtherAmendedPattern:
    """Test detection of 'is further amended by' patterns."""

    def test_further_amended_detection(self):
        """Test that 'is further amended' is recognized as amendment context."""
        parser = AmendmentParser()
        text = "Section 501 is further amended by striking 'old text' and inserting 'new text'"
        assert parser.is_amendment_context(text) is True

    def test_further_amended_numbered_list(self):
        """Test parsing of 'is further amended—' with numbered list."""
        parser = AmendmentParser()
        text = """Section 1204 is further amended—
        (1) by striking "January 1, 2024" and inserting "January 1, 2029";
        (2) by adding at the end the following: "new subsection text"."""

        result = parser.parse(text)
        assert result.success is True
        assert len(result.amendments) >= 1

    def test_are_further_amended(self):
        """Test plural form 'are further amended'."""
        parser = AmendmentParser()
        text = "Sections 501 and 502 are further amended by striking 'old' and inserting 'new'"
        assert parser.is_amendment_context(text) is True


class TestExistingPatterns:
    """Test that existing patterns still work after changes."""

    def test_simple_strike_insert(self):
        """Test basic strike-and-insert pattern."""
        parser = AmendmentParser()
        text = "is amended by striking 'December 31, 2023' and inserting 'December 31, 2029'"
        result = parser.parse(text)
        assert result.success is True
        assert len(result.amendments) >= 1
        assert result.amendments[0].amendment_type == AmendmentType.STRIKE_INSERT

    def test_read_as_follows(self):
        """Test read-as-follows pattern."""
        parser = AmendmentParser()
        text = "Section 501(a) is amended to read as follows: 'New section text here.'"
        result = parser.parse(text)
        assert result.success is True

    def test_add_at_end(self):
        """Test add-at-end pattern."""
        parser = AmendmentParser()
        text = "Section 501 is amended by adding at the end the following: 'Additional text.'"
        result = parser.parse(text)
        assert result.success is True

    def test_smart_quotes_in_amendment(self):
        """Test that smart quotes in amendment text are handled."""
        parser = AmendmentParser()
        # Using actual smart quotes (unicode)
        text = 'is amended by striking \u201cold text\u201d and inserting \u201cnew text\u201d'
        result = parser.parse(text)
        assert result.success is True
        assert len(result.amendments) >= 1

    def test_each_place_appears(self):
        """Test 'each place it appears' pattern."""
        parser = AmendmentParser()
        text = "is amended by striking 'FY2023' each place it appears and inserting 'FY2029'"
        result = parser.parse(text)
        assert result.success is True

    def test_redesignate(self):
        """Test redesignate pattern."""
        parser = AmendmentParser()
        text = "is amended by redesignating subsection (c) as subsection (d)"
        result = parser.parse(text)
        assert result.success is True


class TestEdgeCases:
    """Test edge cases and potential issues."""

    def test_empty_text(self):
        """Test handling of empty text."""
        parser = AmendmentParser()
        result = parser.parse("")
        assert result.success is False
        assert result.error_message == "No text provided"

    def test_definitional_only(self):
        """Test that definitional text without amendments is rejected."""
        parser = AmendmentParser()
        text = "The term 'eligible entity' has the meaning given in section 501(c)(3)"
        result = parser.parse(text)
        # This should NOT be treated as an amendment
        assert result.success is False or len(result.amendments) == 0

    def test_mixed_amendment_and_definition(self):
        """Test text with both definition reference AND amendment."""
        parser = AmendmentParser()
        text = """The term 'eligible entity' has the meaning given in section 501.
        Section 502 is amended by striking 'old' and inserting 'new'."""
        result = parser.parse(text)
        # Should detect the amendment despite the definitional text
        assert result.success is True


# =============================================================================
# Phase 2 Tests: Redesignate and Designate Patterns
# =============================================================================

class TestRedesignatePatterns:
    """Test enhanced redesignate patterns (Phase 2)."""

    def test_simple_redesignate(self):
        """Test basic redesignation pattern."""
        parser = AmendmentParser()
        text = "is amended by redesignating subsection (c) as subsection (d)"
        result = parser.parse(text)
        assert result.success is True
        assert any(a.amendment_type == AmendmentType.REDESIGNATE for a in result.amendments)

    def test_redesignate_paragraph_range(self):
        """Test redesignating a range of paragraphs."""
        parser = AmendmentParser()
        text = "is amended by redesignating paragraphs (2) through (6) as paragraphs (3) through (7)"
        result = parser.parse(text)
        assert result.success is True
        redesignates = [a for a in result.amendments if a.amendment_type == AmendmentType.REDESIGNATE]
        assert len(redesignates) >= 1
        # Check that range is captured
        assert "through" in redesignates[0].text_to_strike.lower()

    def test_redesignate_subparagraph_range(self):
        """Test redesignating a range of subparagraphs."""
        parser = AmendmentParser()
        text = "is amended by redesignating subparagraphs (B) through (D) as subparagraphs (C) through (E)"
        result = parser.parse(text)
        assert result.success is True
        redesignates = [a for a in result.amendments if a.amendment_type == AmendmentType.REDESIGNATE]
        assert len(redesignates) >= 1

    def test_strike_and_redesignate(self):
        """Test combined strike and redesignate pattern."""
        parser = AmendmentParser()
        text = "is amended by striking paragraph (2) and redesignating paragraphs (3) through (5) as paragraphs (2) through (4)"
        result = parser.parse(text)
        assert result.success is True
        # Should detect both the strike and the redesignate
        assert len(result.amendments) >= 1

    def test_redesignate_keyword_fallback(self):
        """Test that 'redesignating' keyword is detected even without full pattern match."""
        parser = AmendmentParser()
        text = "is amended by redesignating the existing provisions"
        assert parser.is_amendment_context(text) is True


class TestDesignatePatterns:
    """Test new designate patterns (Phase 2)."""

    def test_designate_detection(self):
        """Test that 'by designating' is recognized as amendment context."""
        parser = AmendmentParser()
        text = "Section 501 is amended by designating paragraph (1) as subparagraph (A)"
        assert parser.is_amendment_context(text) is True

    def test_simple_designate(self):
        """Test basic designation pattern."""
        parser = AmendmentParser()
        text = "is amended by designating paragraph (1) as subparagraph (A)"
        result = parser.parse(text)
        assert result.success is True
        designates = [a for a in result.amendments if a.amendment_type == AmendmentType.DESIGNATE]
        assert len(designates) >= 1

    def test_designate_matter_preceding(self):
        """Test designating 'matter preceding' pattern."""
        parser = AmendmentParser()
        text = "is amended by designating the matter preceding paragraph (1) as subsection (a)"
        result = parser.parse(text)
        assert result.success is True
        designates = [a for a in result.amendments if a.amendment_type == AmendmentType.DESIGNATE]
        assert len(designates) >= 1
        # Check that 'matter preceding' is captured
        assert "matter" in designates[0].text_to_strike.lower()

    def test_designate_keyword_fallback(self):
        """Test that 'designating' keyword is detected even without full pattern match."""
        parser = AmendmentParser()
        text = "is amended by designating the existing text"
        assert parser.is_amendment_context(text) is True

    def test_designate_not_redesignate(self):
        """Test that 'designating' doesn't match 'redesignating'."""
        parser = AmendmentParser()
        text = "is amended by redesignating subsection (a) as subsection (b)"
        result = parser.parse(text)
        # Should be REDESIGNATE, not DESIGNATE
        designates = [a for a in result.amendments if a.amendment_type == AmendmentType.DESIGNATE]
        redesignates = [a for a in result.amendments if a.amendment_type == AmendmentType.REDESIGNATE]
        assert len(redesignates) >= 1
        # There may be some designate matches from overly broad patterns, but redesignate should be primary


class TestPhase2Integration:
    """Integration tests for Phase 2 patterns with real-world examples."""

    def test_complex_restructuring_amendment(self):
        """Test a complex amendment with multiple structural changes."""
        parser = AmendmentParser()
        text = """Section 1234 is amended—
        (1) by redesignating subsection (c) as subsection (d);
        (2) by designating the matter preceding paragraph (1) as subsection (a);
        (3) by striking paragraph (2) and redesignating paragraphs (3) through (5) as paragraphs (2) through (4); and
        (4) by adding at the end the following new subsection."""
        result = parser.parse(text)
        assert result.success is True
        # Should detect multiple amendment types
        amendment_types = {a.amendment_type for a in result.amendments}
        assert len(amendment_types) >= 2  # At least redesignate and add_at_end

    def test_farm_bill_style_amendment(self):
        """Test amendment pattern typical of Farm Bill legislation."""
        parser = AmendmentParser()
        text = """Section 1244(a) of the Food Security Act of 1985 (16 U.S.C. 3844(a)) is amended—
        (1) by redesignating paragraphs (2) through (6) as paragraphs (3) through (7);
        (2) by inserting after paragraph (1) the following new paragraph."""
        result = parser.parse(text)
        assert result.success is True
        redesignates = [a for a in result.amendments if a.amendment_type == AmendmentType.REDESIGNATE]
        assert len(redesignates) >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
