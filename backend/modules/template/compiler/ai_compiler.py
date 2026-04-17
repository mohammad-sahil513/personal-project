"""
AI-assisted compiler for ambiguous custom-template heading mappings.

This compiler is intentionally designed around an adapter abstraction that can
be backed by Semantic Kernel in the infrastructure layer. Deterministic
heuristics remain the first-pass mechanism; AI is only used for headings that
are ambiguous or unmapped after the heuristic phase.

Prompt source:
- prompts/template/ai_compiler_v1.yaml

Execution-hint policy for this project:
- temperature: forbidden
- max_tokens: forbidden
- allowed alternatives:
    - model_preference
    - reasoning_effort
    - verbosity
    - response_token_budget
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import yaml

from ..contracts.compiler_contracts import (
    AICompilerSuggestion,
    HeuristicMappingCandidate,
    HeuristicMappingResult,
)
from ..models.template_enums import CompilerDecisionSource


class SemanticKernelStructuredAdapter(Protocol):
    """
    Protocol for a Semantic-Kernel-backed structured invocation adapter.

    The concrete implementation can wrap your existing infrastructure SK layer
    while preserving clean business logic in the Template compiler module.
    """

    def invoke_structured(
        self,
        *,
        prompt_template: str,
        input_variables: dict[str, Any],
        execution_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Invoke an LLM call and return a structured mapping/object payload.
        """
        ...


@dataclass(frozen=True, slots=True)
class AICompilerExecutionHints:
    """
    GPT-5 / GPT-5-mini-compatible execution hints for compiler prompts.
    """

    model_preference: str | None = None
    reasoning_effort: str | None = None
    verbosity: str | None = None
    response_token_budget: int | None = None

    def to_payload(self) -> dict[str, Any]:
        """Return a compact dict payload suitable for adapter invocation."""
        return {
            key: value
            for key, value in {
                "model_preference": self.model_preference,
                "reasoning_effort": self.reasoning_effort,
                "verbosity": self.verbosity,
                "response_token_budget": self.response_token_budget,
            }.items()
            if value is not None
        }


class AICompiler:
    """
    AI-assisted heading mapper for ambiguous custom-template sections.

    Behavior:
    - if deterministic heuristics already produced a high-confidence selection,
      this compiler does not intervene,
    - if a heading is ambiguous or unmapped, the compiler asks the SK-backed
      adapter for a bounded suggestion,
    - returned suggestions can then be applied onto heuristic mapping results.
    """

    _PROMPT_BODY_KEYS = ("prompt_template", "template")
    _FORBIDDEN_EXECUTION_HINT_KEYS = frozenset({"temperature", "max_tokens"})
    _ALLOWED_EXECUTION_HINT_KEYS = frozenset(
        {
            "model_preference",
            "reasoning_effort",
            "verbosity",
            "response_token_budget",
        }
    )

    def __init__(
        self,
        *,
        sk_adapter: SemanticKernelStructuredAdapter | None = None,
        project_root: str | Path | None = None,
        prompt_path: str | Path | None = None,
        ambiguity_threshold: float = 0.85,
        logger: logging.Logger | None = None,
    ) -> None:
        resolved_project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[4]
        )

        self._project_root = resolved_project_root
        self._prompt_path = (
            Path(prompt_path).resolve()
            if prompt_path is not None
            else resolved_project_root / "prompts" / "template" / "ai_compiler_v1.yaml"
        )
        self._sk_adapter = sk_adapter
        self._ambiguity_threshold = ambiguity_threshold
        self._logger = logger or logging.getLogger(__name__)

    @property
    def prompt_path(self) -> Path:
        """Return the resolved AI compiler prompt path."""
        return self._prompt_path

    def suggest_mappings(
        self,
        mapping_results: list[HeuristicMappingResult],
    ) -> list[AICompilerSuggestion]:
        """
        Generate AI mapping suggestions for ambiguous or unmapped headings.

        Args:
            mapping_results: Deterministic heuristic mapping results.

        Returns:
            Ordered list of AICompilerSuggestion entries corresponding to the
            ambiguous subset of mapping_results.

        Notes:
        - if no ambiguous headings exist, returns an empty list,
        - if no SK adapter is configured, returns an empty list and logs a warning.
        """
        ambiguous_results = [
            result for result in mapping_results if self._is_ambiguous(result)
        ]
        if not ambiguous_results:
            return []

        if self._sk_adapter is None:
            self._logger.warning(
                "ai_compiler_adapter_missing | %s",
                {"ambiguous_heading_count": len(ambiguous_results)},
            )
            return []

        prompt_payload = self._read_yaml_file(self._prompt_path)
        prompt_template = self._extract_prompt_template(prompt_payload, prompt_path=self._prompt_path)
        execution_hints = self._extract_execution_hints(
            payload=prompt_payload,
            prompt_path=self._prompt_path,
        )

        suggestions: list[AICompilerSuggestion] = []
        self._log_info(
            "ai_compiler_start",
            ambiguous_heading_count=len(ambiguous_results),
            prompt_path=str(self._prompt_path),
        )

        for result in ambiguous_results:
            input_variables = {
                "heading_text": result.heading.raw_text,
                "normalized_heading": result.heading.normalized_text,
                "heading_level": result.heading.level,
                "heuristic_candidates": [
                    {
                        "section_id": candidate.section_id,
                        "title": candidate.title,
                        "confidence": candidate.confidence,
                    }
                    for candidate in result.candidates
                ],
            }

            raw_response = self._sk_adapter.invoke_structured(
                prompt_template=prompt_template,
                input_variables=input_variables,
                execution_hints=execution_hints.to_payload(),
            )
            suggestions.append(self._validate_ai_response(raw_response, heading_text=result.heading.raw_text))

        self._log_info(
            "ai_compiler_completed",
            suggestion_count=len(suggestions),
        )
        return suggestions

    def apply_suggestions(
        self,
        *,
        mapping_results: list[HeuristicMappingResult],
        suggestions: list[AICompilerSuggestion],
    ) -> list[HeuristicMappingResult]:
        """
        Apply ordered AI suggestions onto the ambiguous subset of mapping results.

        The order of `suggestions` is expected to match the order of ambiguous
        mapping results returned by `suggest_mappings`.
        """
        updated_results: list[HeuristicMappingResult] = []
        suggestion_index = 0

        for result in mapping_results:
            if not self._is_ambiguous(result):
                updated_results.append(result)
                continue

            if suggestion_index >= len(suggestions):
                updated_results.append(result)
                continue

            suggestion = suggestions[suggestion_index]
            suggestion_index += 1

            derived_title = self._derive_title_from_section_id(suggestion.suggested_section_id)
            ai_candidate = HeuristicMappingCandidate(
                section_id=suggestion.suggested_section_id,
                title=derived_title,
                confidence=suggestion.confidence,
            )

            candidate_by_id = {candidate.section_id: candidate for candidate in result.candidates}
            candidate_by_id[ai_candidate.section_id] = ai_candidate

            merged_candidates = sorted(
                candidate_by_id.values(),
                key=lambda item: (-item.confidence, item.section_id),
            )

            updated_results.append(
                HeuristicMappingResult(
                    heading=result.heading,
                    candidates=merged_candidates,
                    selected_section_id=suggestion.suggested_section_id,
                    decision_source=CompilerDecisionSource.AI,
                )
            )

        return updated_results

    def _is_ambiguous(self, result: HeuristicMappingResult) -> bool:
        """
        Determine whether a heuristic result should be escalated to AI.
        """
        if result.selected_section_id is None:
            return True

        if not result.candidates:
            return True

        return result.candidates[0].confidence < self._ambiguity_threshold

    @staticmethod
    def _derive_title_from_section_id(section_id: str) -> str:
        """
        Derive a readable title from a section identifier.
        """
        normalized = section_id
        if normalized.startswith("sec_"):
            normalized = normalized[4:]
        normalized = normalized.replace("_", " ").strip()
        return " ".join(token.capitalize() for token in normalized.split())

    def _validate_ai_response(
        self,
        raw_response: dict[str, Any],
        *,
        heading_text: str,
    ) -> AICompilerSuggestion:
        """
        Validate one structured AI response.
        """
        if not isinstance(raw_response, dict):
            raise ValueError("AI compiler adapter response must be a mapping/object.")

        section_id = raw_response.get("suggested_section_id")
        rationale = raw_response.get("rationale")
        confidence = raw_response.get("confidence")

        if not isinstance(section_id, str) or not section_id.strip():
            raise ValueError(
                f"AI compiler response missing `suggested_section_id` for heading `{heading_text}`."
            )
        if not isinstance(rationale, str) or not rationale.strip():
            raise ValueError(
                f"AI compiler response missing `rationale` for heading `{heading_text}`."
            )
        if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
            raise ValueError(
                f"AI compiler response has invalid `confidence` for heading `{heading_text}`."
            )

        return AICompilerSuggestion(
            heading_text=heading_text,
            suggested_section_id=section_id.strip(),
            rationale=rationale.strip(),
            confidence=float(confidence),
        )

    @staticmethod
    def _read_yaml_file(path: Path) -> dict[str, Any]:
        """Read and parse a YAML object file."""
        if not path.exists():
            raise FileNotFoundError(f"AI compiler prompt YAML not found: {path}")

        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in AI compiler prompt: {path}") from exc

        if not isinstance(payload, dict):
            raise ValueError(f"AI compiler prompt YAML must contain a mapping/object root: {path}")

        return payload

    def _extract_prompt_template(self, payload: dict[str, Any], *, prompt_path: Path) -> str:
        """Extract prompt body from YAML."""
        for key in self._PROMPT_BODY_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        raise ValueError(
            f"AI compiler prompt YAML must define one of {self._PROMPT_BODY_KEYS}: {prompt_path}"
        )

    def _extract_execution_hints(
        self,
        *,
        payload: dict[str, Any],
        prompt_path: Path,
    ) -> AICompilerExecutionHints:
        """
        Extract GPT-5-compatible execution hints and forbid unsupported keys.
        """
        raw_hints = payload.get("execution_hints", {})
        if raw_hints is None:
            raw_hints = {}

        if not isinstance(raw_hints, dict):
            raise ValueError(f"`execution_hints` must be a mapping in AI compiler prompt: {prompt_path}")

        forbidden_keys = set(raw_hints).intersection(self._FORBIDDEN_EXECUTION_HINT_KEYS)
        if forbidden_keys:
            raise ValueError(
                "AI compiler prompt contains unsupported execution hint key(s): "
                f"{sorted(forbidden_keys)} in {prompt_path}"
            )

        unknown_keys = set(raw_hints) - self._ALLOWED_EXECUTION_HINT_KEYS
        if unknown_keys:
            raise ValueError(
                f"Unknown execution_hints key(s) in AI compiler prompt: {sorted(unknown_keys)} in {prompt_path}"
            )

        response_token_budget = raw_hints.get("response_token_budget")
        if response_token_budget is not None:
            if not isinstance(response_token_budget, int) or response_token_budget <= 0:
                raise ValueError(
                    f"`response_token_budget` must be a positive integer in AI compiler prompt: {prompt_path}"
                )

        return AICompilerExecutionHints(
            model_preference=self._optional_string(
                raw_hints.get("model_preference"),
                field_name="model_preference",
                prompt_path=prompt_path,
            ),
            reasoning_effort=self._optional_string(
                raw_hints.get("reasoning_effort"),
                field_name="reasoning_effort",
                prompt_path=prompt_path,
            ),
            verbosity=self._optional_string(
                raw_hints.get("verbosity"),
                field_name="verbosity",
                prompt_path=prompt_path,
            ),
            response_token_budget=response_token_budget,
        )

    @staticmethod
    def _optional_string(value: Any, *, field_name: str, prompt_path: Path) -> str | None:
        """Validate an optional non-empty string from YAML."""
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"`{field_name}` must be a non-empty string in {prompt_path}")
        return value.strip()

    def _log_info(self, event_name: str, **payload: object) -> None:
        """Emit a lightweight structured-ish log entry."""
        self._logger.info("%s | %s", event_name, payload)