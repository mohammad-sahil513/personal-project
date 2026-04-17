"""
Asset extraction service for Stage 2.

This service deterministically extracts image-style assets from markdown:
- standard markdown image syntax: ![alt](path-or-url)
- basic HTML image tags: <img src="..." alt="...">

Embedded objects are handled by CleanupService as warning signals rather than
being fully parsed here.
"""

from __future__ import annotations

import re

from backend.modules.ingestion.contracts.stage_2_contracts import (
    AssetRecord,
    AssetRegistry,
    AssetType,
)


class AssetExtractionService:
    """Extract image assets from markdown in a deterministic, testable manner."""

    _MARKDOWN_IMAGE_PATTERN = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)]+)\)")
    _HTML_IMAGE_PATTERN = re.compile(
        r'<img\s+[^>]*src=["\'](?P<src>[^"\']+)["\'][^>]*alt=["\'](?P<alt>[^"\']*)["\'][^>]*>',
        re.IGNORECASE,
    )

    def extract_assets(self, markdown_text: str) -> AssetRegistry:
        """Extract image assets from markdown and return a deterministic registry."""
        assets: list[AssetRecord] = []
        line_starts = self._build_line_starts(markdown_text)

        matches: list[tuple[int, str, str | None, str | None]] = []

        for match in self._MARKDOWN_IMAGE_PATTERN.finditer(markdown_text):
            matches.append(
                (
                    match.start(),
                    match.group(0),
                    match.group("alt"),
                    match.group("src"),
                )
            )

        for match in self._HTML_IMAGE_PATTERN.finditer(markdown_text):
            matches.append(
                (
                    match.start(),
                    match.group(0),
                    match.group("alt"),
                    match.group("src"),
                )
            )

        matches.sort(key=lambda item: item[0])

        for occurrence_index, (char_position, placeholder, alt_text, src) in enumerate(matches, start=1):
            line_number = self._line_number_for_position(char_position, line_starts)
            assets.append(
                AssetRecord(
                    asset_id=f"asset_{occurrence_index:03d}",
                    asset_type=AssetType.IMAGE,
                    alt_text=alt_text or None,
                    source_reference=src or None,
                    placeholder=placeholder,
                    occurrence_index=occurrence_index,
                    line_number=line_number,
                )
            )

        return AssetRegistry(assets=assets)

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