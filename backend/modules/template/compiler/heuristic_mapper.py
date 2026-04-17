"""
Deterministic heuristic mapper for custom template headings.

This service reads configurable heading-pattern rules from YAML and maps
normalized headings to likely internal section identifiers before any future
AI-assisted compiler step is used.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ..contracts.compiler_contracts import (
    ExtractedHeading,
    HeuristicMappingCandidate,
    HeuristicMappingResult,
)
from .header_normalizer import HeaderNormalizer


@dataclass(frozen=True, slots=True)
class _PatternRule:
    """Internal representation of one heuristic mapping rule."""

    section_id: str
    title: str
    patterns: tuple[str, ...]


class HeuristicMapper:
    """
    Deterministic heading mapper driven by YAML-configured patterns.

    Supported YAML shapes:
    - top-level list of rule objects
    - top-level dict with `patterns` or `sections`
    """

    def __init__(
        self,
        *,
        project_root: str | Path | None = None,
        config_path: str | Path | None = None,
        header_normalizer: HeaderNormalizer | None = None,
        minimum_candidate_score: float = 0.50,
    ) -> None:
        resolved_project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[4]
        )

        self._project_root = resolved_project_root
        self._config_path = (
            Path(config_path).resolve()
            if config_path is not None
            else resolved_project_root / "config" / "heuristic_patterns.yaml"
        )
        self._header_normalizer = header_normalizer or HeaderNormalizer()
        self._minimum_candidate_score = minimum_candidate_score

    @property
    def config_path(self) -> Path:
        """Return the resolved heuristic config path."""
        return self._config_path

    def map_heading(self, heading: ExtractedHeading) -> HeuristicMappingResult:
        """
        Map one extracted heading to deterministic section candidates.
        """
        rules = self._load_rules()
        candidates: list[HeuristicMappingCandidate] = []

        for rule in rules:
            best_score = 0.0
            for pattern in rule.patterns:
                score = self._score_match(heading.normalized_text, pattern)
                best_score = max(best_score, score)

            if best_score >= self._minimum_candidate_score:
                candidates.append(
                    HeuristicMappingCandidate(
                        section_id=rule.section_id,
                        title=rule.title,
                        confidence=round(best_score, 4),
                    )
                )

        candidates.sort(key=lambda item: (-item.confidence, item.section_id))
        selected_section_id = candidates[0].section_id if candidates else None

        return HeuristicMappingResult(
            heading=heading,
            candidates=candidates,
            selected_section_id=selected_section_id,
        )

    def map_headings(self, headings: list[ExtractedHeading]) -> list[HeuristicMappingResult]:
        """
        Map a list of extracted headings in order.
        """
        return [self.map_heading(heading) for heading in headings]

    def _load_rules(self) -> list[_PatternRule]:
        """Load and normalize heuristic mapping rules from YAML."""
        if not self._config_path.exists():
            raise FileNotFoundError(f"Heuristic pattern config not found: {self._config_path}")

        try:
            with self._config_path.open("r", encoding="utf-8") as handle:
                payload = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in heuristic pattern config: {self._config_path}") from exc

        raw_rules: Any
        if isinstance(payload, list):
            raw_rules = payload
        elif isinstance(payload, dict):
            raw_rules = payload.get("patterns") or payload.get("sections") or []
        else:
            raise ValueError(
                f"Heuristic pattern config must be a list or mapping root: {self._config_path}"
            )

        if not isinstance(raw_rules, list):
            raise ValueError(
                f"Heuristic pattern config rule list is invalid: {self._config_path}"
            )

        rules: list[_PatternRule] = []
        for index, item in enumerate(raw_rules):
            if not isinstance(item, dict):
                raise ValueError(
                    f"Heuristic rule at index {index} must be a mapping: {self._config_path}"
                )

            section_id = item.get("section_id")
            title = item.get("title")
            patterns = item.get("patterns")

            if not isinstance(section_id, str) or not section_id.strip():
                raise ValueError(f"Heuristic rule missing `section_id` at index {index}")
            if not isinstance(title, str) or not title.strip():
                raise ValueError(f"Heuristic rule missing `title` at index {index}")
            if not isinstance(patterns, list) or not patterns:
                raise ValueError(f"Heuristic rule missing `patterns` at index {index}")

            normalized_patterns = tuple(
                self._header_normalizer.normalize(pattern)
                for pattern in patterns
                if isinstance(pattern, str) and pattern.strip()
            )
            if not normalized_patterns:
                raise ValueError(f"Heuristic rule has no usable `patterns` at index {index}")

            rules.append(
                _PatternRule(
                    section_id=section_id.strip(),
                    title=title.strip(),
                    patterns=normalized_patterns,
                )
            )

        return rules

    def _score_match(self, normalized_heading: str, normalized_pattern: str) -> float:
        """
        Score one heading-pattern pair deterministically.

        Score bands:
        - 1.00 exact match
        - 0.90 substring match
        - 0.75 high token overlap
        - 0.60 moderate token overlap
        - 0.00 otherwise
        """
        if normalized_heading == normalized_pattern:
            return 1.00

        if normalized_pattern in normalized_heading or normalized_heading in normalized_pattern:
            return 0.90

        heading_tokens = set(normalized_heading.split())
        pattern_tokens = set(normalized_pattern.split())
        if not heading_tokens or not pattern_tokens:
            return 0.0

        overlap_ratio = len(heading_tokens & pattern_tokens) / len(pattern_tokens)
        if overlap_ratio >= 0.80:
            return 0.75
        if overlap_ratio >= 0.60:
            return 0.60

        return 0.0
