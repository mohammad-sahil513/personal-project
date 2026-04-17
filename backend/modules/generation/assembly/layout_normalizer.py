"""
Layout normalizer for the Generation module.

Responsibilities:
- Perform structural normalization on assembled markdown
- Normalize heading/paragraph/table/placeholder/diagram-marker spacing
- Keep output deterministic and idempotent

Important:
- This file is structural-only normalization.
- It does NOT apply visual styling, DOCX styles, or rendering-specific layout rules.
- It assumes the markdown contract has already been validated upstream.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field


class LayoutNormalizationRequest(BaseModel):
    """
    Input payload for structural normalization of assembled markdown.
    """

    model_config = ConfigDict(extra="forbid")

    assembled_markdown: str = Field(
        default="",
        description="Document-level assembled markdown to normalize.",
    )
    ensure_trailing_newline: bool = Field(
        default=True,
        description="Whether to ensure the normalized output ends with a newline.",
    )


class LayoutNormalizationResult(BaseModel):
    """
    Result of structural normalization.
    """

    model_config = ConfigDict(extra="forbid")

    normalized_markdown: str = Field(
        default="",
        description="Structurally normalized assembled markdown.",
    )
    changed: bool = Field(
        default=False,
        description="Whether normalization changed the input markdown.",
    )


class LayoutNormalizer:
    """
    Deterministic structural normalizer for assembled Generation markdown.

    Rules applied:
    - normalize CRLF/CR to LF
    - trim trailing whitespace from every line
    - collapse 3+ blank lines to at most 2
    - ensure headings are surrounded by a single blank line boundary
    - ensure placeholder blocks and diagram markers are separated cleanly
    - preserve markdown table rows without injecting extra blank lines inside a table
    - ensure optional trailing newline
    """

    _HEADING_RE = re.compile(r"^(##|###)\s+")
    _DIAGRAM_MARKER_RE = re.compile(r"^\[\[DIAGRAM:[^\]]+\]\]$")
    _PLACEHOLDER_RE = re.compile(r"^\[PLACEHOLDER\]$")

    def normalize(self, request: LayoutNormalizationRequest) -> LayoutNormalizationResult:
        """
        Normalize assembled markdown structure deterministically.
        """
        original = request.assembled_markdown or ""
        text = self._normalize_newlines(original)
        text = self._strip_trailing_spaces(text)
        lines = text.split("\n")

        normalized_lines = self._normalize_line_structure(lines)
        normalized = "\n".join(normalized_lines)
        normalized = self._collapse_excess_blank_lines(normalized)

        if request.ensure_trailing_newline:
            if normalized and not normalized.endswith("\n"):
                normalized += "\n"

        changed = normalized != original
        return LayoutNormalizationResult(
            normalized_markdown=normalized,
            changed=changed,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _normalize_newlines(self, text: str) -> str:
        """
        Normalize CRLF / CR line endings to LF.
        """
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def _strip_trailing_spaces(self, text: str) -> str:
        """
        Remove trailing whitespace from each line.
        """
        return "\n".join(line.rstrip() for line in text.split("\n"))

    def _normalize_line_structure(self, lines: list[str]) -> list[str]:
        """
        Apply deterministic structural spacing rules while preserving table continuity.
        """
        output: list[str] = []
        in_table = False

        for idx, raw_line in enumerate(lines):
            line = raw_line.strip()

            # Preserve true blank lines, but let later collapse handle excessive runs.
            if not line:
                # avoid stacking unnecessary blanks in a table block
                if in_table:
                    in_table = False
                output.append("")
                continue

            is_table_line = line.startswith("|") and line.endswith("|")
            is_heading = bool(self._HEADING_RE.match(line))
            is_diagram_marker = bool(self._DIAGRAM_MARKER_RE.match(line))
            is_placeholder = bool(self._PLACEHOLDER_RE.match(line))

            if is_heading:
                self._ensure_blank_before(output)
                output.append(line)
                self._ensure_blank_after(output)
                in_table = False
                continue

            if is_diagram_marker or is_placeholder:
                self._ensure_blank_before(output)
                output.append(line)
                self._ensure_blank_after(output)
                in_table = False
                continue

            if is_table_line:
                # if entering a table block, ensure a blank line before it
                if not in_table:
                    self._ensure_blank_before(output)
                output.append(line)
                in_table = True
                continue

            # regular paragraph / prose line
            if in_table:
                # close table block cleanly before paragraph
                self._ensure_blank_before(output)
                in_table = False

            output.append(line)

        # Final cleanup for accidental extra blanks at beginning/end
        while output and output[0] == "":
            output.pop(0)
        while output and output[-1] == "":
            output.pop()

        return output

    def _ensure_blank_before(self, lines: list[str]) -> None:
        """
        Ensure there is exactly one blank-line boundary before a structural block
        when the current output isn't already separated.
        """
        if not lines:
            return
        if lines[-1] != "":
            lines.append("")

    def _ensure_blank_after(self, lines: list[str]) -> None:
        """
        Ensure there is a blank-line boundary after a structural block.
        """
        if not lines:
            return
        if lines[-1] != "":
            lines.append("")

    def _collapse_excess_blank_lines(self, text: str) -> str:
        """
        Collapse 3+ consecutive blank lines into at most 2.
        """
        return re.sub(r"\n{3,}", "\n\n", text)
