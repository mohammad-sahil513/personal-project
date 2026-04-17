"""
PlantUML validator for the Generation module.

Responsibilities:
- Validate normalized PlantUML source before render attempts
- Perform deterministic structural/lint checks
- Reject risky remote include usage by default
- Return a simple (is_valid, issues) tuple for downstream orchestration

Important:
- This file is validation-only.
- It does NOT normalize, render, repair, or persist artifacts.
- It intentionally performs lightweight deterministic checks rather than
  full semantic parsing of PlantUML.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PlantUMLValidationConfig:
    """
    Lightweight validation options for PlantUML source.

    Defaults are intentionally conservative for PoC/runtime safety.
    """

    allow_remote_includeurl: bool = False
    require_start_end_wrappers: bool = True
    require_non_empty_body: bool = True
    max_source_chars: int = 100_000


class PlantUMLValidatorService:
    """
    Deterministic validator/linter for normalized PlantUML source text.

    Checks performed:
    - non-empty content
    - max source size
    - @startuml / @enduml presence and ordering
    - non-empty body between wrappers
    - balanced code fence absence (markdown fences should already be stripped)
    - remote !includeurl rejection by default
    - basic duplicate-wrapper sanity checks
    """

    _START_RE = re.compile(r"^\s*@startuml\b", re.IGNORECASE | re.MULTILINE)
    _END_RE = re.compile(r"^\s*@enduml\b", re.IGNORECASE | re.MULTILINE)
    _INCLUDEURL_RE = re.compile(r"^\s*!includeurl\b", re.IGNORECASE | re.MULTILINE)
    _CODE_FENCE_RE = re.compile(r"^\s*```", re.MULTILINE)

    def __init__(self, config: PlantUMLValidationConfig | None = None) -> None:
        self.config = config or PlantUMLValidationConfig()

    def validate(self, puml_text: str) -> tuple[bool, list[str]]:
        """
        Validate normalized PlantUML source text.

        Returns:
            (is_valid, issues)

        Notes:
        - `issues` contains deterministic human-readable messages.
        - `is_valid` is True only when no blocking issues are found.
        """
        issues: list[str] = []

        if puml_text is None:
            return False, ["PlantUML source cannot be None."]

        if not isinstance(puml_text, str):
            return False, ["PlantUML source must be a string."]

        text = puml_text.strip()

        if not text:
            return False, ["PlantUML source is empty."]

        if len(text) > self.config.max_source_chars:
            issues.append(
                f"PlantUML source exceeds max allowed size ({self.config.max_source_chars} characters)."
            )

        # Markdown fences should already be removed by the normalizer.
        if self._CODE_FENCE_RE.search(text):
            issues.append(
                "PlantUML source still contains markdown code fences; normalize before validation."
            )

        start_matches = list(self._START_RE.finditer(text))
        end_matches = list(self._END_RE.finditer(text))

        if self.config.require_start_end_wrappers:
            if not start_matches:
                issues.append("Missing @startuml boundary.")
            if not end_matches:
                issues.append("Missing @enduml boundary.")

        if start_matches and end_matches:
            first_start = start_matches[0].start()
            last_end = end_matches[-1].start()

            if first_start > last_end:
                issues.append("@startuml appears after @enduml.")

            if len(start_matches) > 1:
                issues.append("Multiple @startuml boundaries found.")
            if len(end_matches) > 1:
                issues.append("Multiple @enduml boundaries found.")

            if self.config.require_non_empty_body:
                body = self._extract_body(text, first_start, last_end)
                if not body.strip():
                    issues.append("PlantUML body is empty between @startuml and @enduml.")

        if not self.config.allow_remote_includeurl and self._INCLUDEURL_RE.search(text):
            issues.append("Remote !includeurl is not allowed.")

        return len(issues) == 0, issues

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _extract_body(self, text: str, first_start_index: int, last_end_index: int) -> str:
        """
        Extract the body between the first @startuml and the last @enduml.

        This assumes the caller already confirmed both boundaries exist.
        """
        lines = text.splitlines()

        start_line_idx = None
        end_line_idx = None

        for idx, line in enumerate(lines):
            if start_line_idx is None and re.match(r"^\s*@startuml\b", line, re.IGNORECASE):
                start_line_idx = idx
            if re.match(r"^\s*@enduml\b", line, re.IGNORECASE):
                end_line_idx = idx

        if start_line_idx is None or end_line_idx is None or end_line_idx <= start_line_idx:
            return ""

        return "\n".join(lines[start_line_idx + 1 : end_line_idx])