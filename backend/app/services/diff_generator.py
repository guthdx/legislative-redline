"""
Diff Generator Service

Generates visual redline comparisons between original and amended text
using word-level diffs with proper HTML output.

Output uses standard redline conventions:
- Deletions: <del class="redline-deleted">text</del> (red strikethrough)
- Insertions: <ins class="redline-inserted">text</ins> (green highlight)
- Unchanged: plain text

Uses Google's diff-match-patch library for robust text comparison.
"""

import html
import logging
from dataclasses import dataclass
from typing import List, Tuple
from enum import Enum

from diff_match_patch import diff_match_patch

logger = logging.getLogger(__name__)


class DiffOperation(int, Enum):
    """Diff operation types matching diff-match-patch constants."""
    DELETE = -1
    EQUAL = 0
    INSERT = 1


@dataclass
class DiffResult:
    """Result of diff generation."""
    html: str
    deletions_count: int = 0
    insertions_count: int = 0
    has_changes: bool = False
    original_length: int = 0
    amended_length: int = 0


class DiffGenerator:
    """
    Generates visual redline comparisons between original and amended text.

    Usage:
        generator = DiffGenerator()
        result = generator.generate(original_text, amended_text)
        print(result.html)  # HTML with <del> and <ins> tags
    """

    def __init__(
        self,
        semantic_cleanup: bool = True,
        efficiency_cleanup: bool = True,
        edit_cost: int = 4
    ):
        """
        Initialize the diff generator.

        Args:
            semantic_cleanup: Clean up diffs for human readability
            efficiency_cleanup: Clean up diffs for machine efficiency
            edit_cost: Cost threshold for edit cleanup (higher = more consolidation)
        """
        self.dmp = diff_match_patch()
        self.semantic_cleanup = semantic_cleanup
        self.efficiency_cleanup = efficiency_cleanup
        self.edit_cost = edit_cost

    def generate(
        self,
        original: str,
        amended: str,
        context_lines: int = 0,
        max_length: int = 0
    ) -> DiffResult:
        """
        Generate an HTML diff between original and amended text.

        Args:
            original: The original text
            amended: The amended text
            context_lines: Not used (for API compatibility)
            max_length: If > 0, truncate texts longer than this

        Returns:
            DiffResult with HTML diff and statistics
        """
        # Handle empty inputs
        if not original and not amended:
            return DiffResult(
                html='<span class="redline-unchanged">No text to compare.</span>',
                has_changes=False
            )

        if not original:
            escaped = html.escape(amended)
            if max_length and len(escaped) > max_length:
                escaped = escaped[:max_length] + "..."
            return DiffResult(
                html=f'<ins class="redline-inserted">{escaped}</ins>',
                insertions_count=len(amended.split()),
                has_changes=True,
                amended_length=len(amended)
            )

        if not amended:
            escaped = html.escape(original)
            if max_length and len(escaped) > max_length:
                escaped = escaped[:max_length] + "..."
            return DiffResult(
                html=f'<del class="redline-deleted">{escaped}</del>',
                deletions_count=len(original.split()),
                has_changes=True,
                original_length=len(original)
            )

        # Truncate if needed
        if max_length:
            original = original[:max_length]
            amended = amended[:max_length]

        # Compute diff
        diffs = self.dmp.diff_main(original, amended)

        # Apply cleanups for better readability
        if self.semantic_cleanup:
            self.dmp.diff_cleanupSemantic(diffs)

        if self.efficiency_cleanup:
            self.dmp.diff_cleanupEfficiency(diffs)

        # Convert to HTML
        html_parts = []
        deletions = 0
        insertions = 0

        for op, text in diffs:
            escaped_text = html.escape(text)

            if op == DiffOperation.DELETE:
                html_parts.append(f'<del class="redline-deleted">{escaped_text}</del>')
                deletions += len(text.split())
            elif op == DiffOperation.INSERT:
                html_parts.append(f'<ins class="redline-inserted">{escaped_text}</ins>')
                insertions += len(text.split())
            else:  # EQUAL
                html_parts.append(escaped_text)

        html_output = "".join(html_parts)
        has_changes = deletions > 0 or insertions > 0

        return DiffResult(
            html=html_output,
            deletions_count=deletions,
            insertions_count=insertions,
            has_changes=has_changes,
            original_length=len(original),
            amended_length=len(amended)
        )

    def generate_side_by_side(
        self,
        original: str,
        amended: str,
        max_length: int = 0
    ) -> Tuple[str, str]:
        """
        Generate side-by-side diff HTML for two-column display.

        Args:
            original: The original text
            amended: The amended text
            max_length: If > 0, truncate texts longer than this

        Returns:
            Tuple of (original_html, amended_html) with appropriate highlighting
        """
        if max_length:
            original = original[:max_length]
            amended = amended[:max_length]

        diffs = self.dmp.diff_main(original, amended)

        if self.semantic_cleanup:
            self.dmp.diff_cleanupSemantic(diffs)

        original_parts = []
        amended_parts = []

        for op, text in diffs:
            escaped = html.escape(text)

            if op == DiffOperation.DELETE:
                original_parts.append(f'<del class="redline-deleted">{escaped}</del>')
                # Don't add to amended
            elif op == DiffOperation.INSERT:
                amended_parts.append(f'<ins class="redline-inserted">{escaped}</ins>')
                # Don't add to original
            else:  # EQUAL
                original_parts.append(escaped)
                amended_parts.append(escaped)

        return "".join(original_parts), "".join(amended_parts)

    def generate_unified(
        self,
        original: str,
        amended: str,
        context_words: int = 5
    ) -> str:
        """
        Generate unified diff with context, similar to git diff.

        Shows changes with surrounding context words for clarity.

        Args:
            original: The original text
            amended: The amended text
            context_words: Number of context words to show around changes

        Returns:
            HTML string with context-aware diff
        """
        diffs = self.dmp.diff_main(original, amended)

        if self.semantic_cleanup:
            self.dmp.diff_cleanupSemantic(diffs)

        html_parts = []
        buffer = []
        in_change_region = False

        for op, text in diffs:
            escaped = html.escape(text)

            if op == DiffOperation.EQUAL:
                words = text.split()
                if in_change_region:
                    # Show context after change
                    context = " ".join(words[:context_words])
                    if context:
                        html_parts.append(html.escape(context))
                    if len(words) > context_words * 2:
                        html_parts.append('<span class="redline-ellipsis">...</span>')
                    in_change_region = False
                    buffer = words[-context_words:] if len(words) > context_words else []
                else:
                    # Buffer context before change
                    buffer = words[-context_words:] if len(words) > context_words else words
            else:
                if buffer:
                    html_parts.append(html.escape(" ".join(buffer)) + " ")
                    buffer = []

                if op == DiffOperation.DELETE:
                    html_parts.append(f'<del class="redline-deleted">{escaped}</del>')
                else:  # INSERT
                    html_parts.append(f'<ins class="redline-inserted">{escaped}</ins>')

                in_change_region = True

        return "".join(html_parts)


def generate_redline_html(
    original: str,
    amended: str,
    amendment_type: str = None,
    max_length: int = 2000
) -> str:
    """
    Convenience function to generate redline HTML.

    Args:
        original: Original statute text
        amended: Amended text after applying changes
        amendment_type: Optional amendment type for display
        max_length: Maximum text length (0 = no limit)

    Returns:
        HTML string with redline markup
    """
    generator = DiffGenerator()
    result = generator.generate(original, amended, max_length=max_length)

    # Wrap in container with metadata
    type_note = f'<p class="redline-type">Amendment type: {amendment_type}</p>' if amendment_type else ""

    if not result.has_changes:
        return f'''
<div class="redline-container">
    {type_note}
    <p class="redline-note">No changes detected between original and amended text.</p>
    <div class="redline-content">{result.html}</div>
</div>
'''

    return f'''
<div class="redline-container">
    {type_note}
    <p class="redline-stats">
        <span class="redline-deletions">{result.deletions_count} deletion(s)</span>
        <span class="redline-insertions">{result.insertions_count} insertion(s)</span>
    </p>
    <div class="redline-content">{result.html}</div>
</div>
'''
