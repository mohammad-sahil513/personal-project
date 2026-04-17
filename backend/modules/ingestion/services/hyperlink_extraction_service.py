"""
Hyperlink extraction service for Stage 2.

This service extracts standard markdown links while intentionally excluding
image links because they are handled separately by AssetExtractionService.
"""

from __future__ import annotations

import re

from backend.modules.ingestion.contracts.stage_2_contracts import (
    HyperlinkRecord,
    HyperlinkRegistry,
)


class HyperlinkExtractionService:
    """Extract non-image markdown hyperlinks in a deterministic way."""

    _HYPERLINK_PATTERN = re.compile(r"(?<!!)\[(?P<label>[^\]]+)\]\((?P<url>[^)]+)\)")

    def extract_hyperlinks(self, markdown_text: str) -> HyperlinkRegistry:
        """Extract markdown hyperlinks from the provided text."""
        hyperlinks: list[HyperlinkRecord] = []
        line_starts = self._build_line_starts(markdown_text)

        for occurrence_index, match in enumerate(self._HYPERLINK_PATTERN.finditer(markdown_text), start=1):
            hyperlinks.append(
                HyperlinkRecord(
                    hyperlink_id=f"hyperlink_{occurrence_index:03d}",
                    label=match.group("label").strip(),
                    url=match.group("url").strip(),
                    occurrence_index=occurrence_index,
                    line_number=self._line_number_for_position(match.start(), line_starts),
                )
            )

        return HyperlinkRegistry(hyperlinks=hyperlinks)

    @staticmethod
    def _build_line_starts(text: str) -> list[int]:
        starts = [0]
        for index, character in enumerate(text):
            if character == "\n":
                starts.append(index + 1)
        return starts

    @staticmethod
    def _line_number_for_position(position: int, line_starts: list[int]) -> int:
        line_number = 1
        for index, start in enumerate(line_starts):
            if start > position:
                break
            line_number = index + 1
        return line_number