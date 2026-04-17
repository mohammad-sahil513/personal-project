"""
Cleanup service for Stage 2 markdown enrichment.

Responsibilities:
- normalize line endings and trailing whitespace
- collapse excessive blank lines
- remove repeated header/footer noise heuristically
- detect embedded object signals as warnings
"""

from __future__ import annotations

import re
from collections import Counter

from backend.modules.ingestion.contracts.stage_1_contracts import StageWarning


class CleanupService:
    """Apply deterministic cleanup rules to parsed markdown."""

    _EMBEDDED_OBJECT_PATTERN = re.compile(
        r"\b(embedded object|ole object|package object|visio drawing object)\b",
        re.IGNORECASE,
    )

    _PAGE_NOISE_PATTERN = re.compile(
        r"^\s*(page\s+\d+(\s+of\s+\d+)?|\d+)\s*$",
        re.IGNORECASE,
    )

    _COMMON_FOOTER_TERMS = ("confidential", "copyright", "all rights reserved")

    def clean_markdown(self, markdown_text: str) -> tuple[str, list[StageWarning], int]:
        """
        Clean markdown and return:
        - cleaned markdown text
        - warning list
        - embedded object count
        """
        normalized = markdown_text.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.rstrip() for line in normalized.split("\n")]

        repeated_line_counts = Counter(
            line.strip()
            for line in lines
            if line.strip() and not line.lstrip().startswith("#") and len(line.strip()) <= 120
        )

        lines_to_remove = {
            line
            for line, count in repeated_line_counts.items()
            if count >= 3 and self._looks_like_header_footer_noise(line)
        }

        cleaned_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped in lines_to_remove:
                continue
            cleaned_lines.append(line)

        cleaned_text = "\n".join(cleaned_lines)
        cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()

        warnings: list[StageWarning] = []
        embedded_object_matches = list(self._EMBEDDED_OBJECT_PATTERN.finditer(cleaned_text))
        if embedded_object_matches:
            warnings.append(
                StageWarning(
                    code="EMBEDDED_OBJECT_DETECTED",
                    message="Embedded-object-style content was detected in the parsed markdown.",
                    details={"embedded_object_count": len(embedded_object_matches)},
                )
            )

        return cleaned_text, warnings, len(embedded_object_matches)

    def _looks_like_header_footer_noise(self, line: str) -> bool:
        lowered = line.lower()

        if self._PAGE_NOISE_PATTERN.match(line):
            return True

        return any(term in lowered for term in self._COMMON_FOOTER_TERMS)