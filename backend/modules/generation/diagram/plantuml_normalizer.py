"""
PlantUML normalizer for the Generation module.

Responsibilities:
- Normalize raw/generated PlantUML text into a stable canonical form
- Remove common LLM formatting noise (markdown fences, BOM, trailing spaces)
- Normalize line endings
- Ensure @startuml / @enduml boundaries exist
- Apply deterministic whitespace cleanup

Important:
- This file is normalization-only.
- It does NOT validate semantic correctness beyond basic source-shape normalization.
- It does NOT render, repair, or persist artifacts.
"""

from __future__ import annotations

import re


class PlantUMLNormalizerService:
    """
    Deterministic normalizer for PlantUML source text.

    Practical normalization rules:
    - strip leading/trailing whitespace
    - remove UTF-8 BOM if present
    - unwrap fenced markdown/code blocks
    - normalize CRLF/CR to LF
    - trim trailing spaces per line
    - collapse excessive blank lines
    - ensure @startuml / @enduml wrappers exist
    """

    _FENCE_START_RE = re.compile(r"^```(?:plantuml|puml|uml|markdown)?\s*$", re.IGNORECASE)
    _FENCE_END_RE = re.compile(r"^```\s*$")

    def normalize(self, puml_text: str) -> str:
        """
        Normalize raw/generated PlantUML text into canonical form.
        """
        if puml_text is None:
            raise ValueError("puml_text cannot be None.")

        normalized = self._remove_bom(puml_text)
        normalized = self._normalize_newlines(normalized)
        normalized = normalized.strip()

        if not normalized:
            raise ValueError("puml_text cannot be empty after trimming.")

        normalized = self._unwrap_code_fences(normalized)
        normalized = self._normalize_newlines(normalized)
        normalized = self._strip_trailing_spaces(normalized)
        normalized = self._collapse_excess_blank_lines(normalized)
        normalized = self._ensure_boundaries(normalized)
        normalized = self._strip_trailing_spaces(normalized).strip()

        if not normalized:
            raise ValueError("Normalized PlantUML text is empty.")

        return normalized + "\n"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _remove_bom(self, text: str) -> str:
        """
        Remove UTF-8 BOM if present.
        """
        return text.lstrip("\ufeff")

    def _normalize_newlines(self, text: str) -> str:
        """
        Normalize CRLF / CR to LF.
        """
        return text.replace("\r\n", "\n").replace("\r", "\n")

    def _unwrap_code_fences(self, text: str) -> str:
        """
        Remove surrounding markdown/code fences when present.

        Examples:
        ```plantuml
        @startuml
        ...
        @enduml
        ```

        or
        ```
        @startuml
        ...
        @enduml
        ```
        """
        lines = text.split("\n")
        if len(lines) >= 2 and self._FENCE_START_RE.match(lines[0].strip()) and self._FENCE_END_RE.match(lines[-1].strip()):
            body = "\n".join(lines[1:-1]).strip()
            return body
        return text

    def _strip_trailing_spaces(self, text: str) -> str:
        """
        Remove trailing whitespace from each line.
        """
        return "\n".join(line.rstrip() for line in text.split("\n"))

    def _collapse_excess_blank_lines(self, text: str) -> str:
        """
        Collapse runs of 3+ blank lines into at most 2 blank lines.
        """
        return re.sub(r"\n{3,}", "\n\n", text)

    def _ensure_boundaries(self, text: str) -> str:
        """
        Ensure PlantUML source is wrapped with @startuml and @enduml.

        If either boundary is missing, add it deterministically.
        """
        stripped = text.strip()

        has_start = stripped.lower().startswith("@startuml")
        has_end = stripped.lower().endswith("@enduml")

        lines = stripped.split("\n")

        if not has_start:
            lines.insert(0, "@startuml")

        if not has_end:
            lines.append("@enduml")

        return "\n".join(lines)