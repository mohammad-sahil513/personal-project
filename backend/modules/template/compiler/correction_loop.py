"""
Bounded correction loop for compiled custom templates.

This correction loop runs after semantic validation and attempts to repair
common compiler issues while preserving section identity and the current-sprint
runtime constraints.

Correction policy:
- deterministic fixes are attempted first,
- optional SK-backed structured correction can be used afterward if configured,
- no correction may introduce `diagram_plantuml`,
- section_id values are never changed,
- bounded retries only.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol

import yaml

from ..contracts.compiler_contracts import CorrectionLoopResult
from ..contracts.section_contracts import RetrievalBinding
from ..contracts.template_contracts import PromptReference, TemplateDefinition
from ..models.template_enums import GenerationStrategy
from .header_normalizer import HeaderNormalizer
from .semantic_validator import SemanticValidator


class SemanticKernelCorrectionAdapter(Protocol):
    """
    Protocol for optional SK-backed correction suggestions.
    """

    def invoke_structured(
        self,
        *,
        prompt_template: str,
        input_variables: dict[str, Any],
        execution_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Invoke the correction model and return a structured patch payload.
        """
        ...


class CorrectionLoop:
    """
    Bounded correction loop for compiled TemplateDefinition artifacts.
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
        semantic_validator: SemanticValidator | None = None,
        sk_adapter: SemanticKernelCorrectionAdapter | None = None,
        header_normalizer: HeaderNormalizer | None = None,
        project_root: str | Path | None = None,
        prompt_path: str | Path | None = None,
        default_retrieval_profile_name: str = "default_profile",
        max_iterations: int = 2,
        logger: logging.Logger | None = None,
    ) -> None:
        resolved_project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[4]
        )

        self._semantic_validator = semantic_validator or SemanticValidator()
        self._sk_adapter = sk_adapter
        self._header_normalizer = header_normalizer or HeaderNormalizer()
        self._project_root = resolved_project_root
        self._prompt_path = (
            Path(prompt_path).resolve()
            if prompt_path is not None
            else resolved_project_root / "prompts" / "template" / "correction_loop_v1.yaml"
        )
        self._default_retrieval_profile_name = default_retrieval_profile_name
        self._max_iterations = max_iterations
        self._logger = logger or logging.getLogger(__name__)

    def correct_template(
        self,
        template_definition: TemplateDefinition,
        *,
        requirement_ids_filter_supported: bool = False,
    ) -> tuple[TemplateDefinition, CorrectionLoopResult]:
        """
        Attempt bounded correction of a compiled template.

        Returns:
            A tuple of:
            - corrected (or original) TemplateDefinition
            - CorrectionLoopResult summary
        """
        working_template = template_definition.model_copy(deep=True)
        warnings: list[str] = []
        corrected = False
        iterations_used = 0

        self._log_info(
            "compiler_correction_loop_start",
            template_id=working_template.metadata.template_id,
            template_version=working_template.metadata.version,
            max_iterations=self._max_iterations,
        )

        for iteration in range(1, self._max_iterations + 1):
            semantic_result = self._semantic_validator.validate_compiled_template(
                working_template,
                requirement_ids_filter_supported=requirement_ids_filter_supported,
            )
            if semantic_result.is_valid:
                iterations_used = iteration - 1
                break

            changed = self._apply_deterministic_fixes(working_template, warnings)
            ai_changed = False

            if not changed and self._sk_adapter is not None:
                ai_changed = self._apply_ai_corrections(
                    working_template,
                    semantic_errors=semantic_result.errors,
                    warnings=warnings,
                )

            if not changed and not ai_changed:
                iterations_used = iteration
                warnings.append("Correction loop stopped because no additional safe fixes were available.")
                break

            corrected = corrected or changed or ai_changed
            iterations_used = iteration

        final_semantic = self._semantic_validator.validate_compiled_template(
            working_template,
            requirement_ids_filter_supported=requirement_ids_filter_supported,
        )

        if not final_semantic.is_valid:
            warnings.append("Compiled template remains semantically invalid after bounded correction attempts.")

        self._log_info(
            "compiler_correction_loop_completed",
            template_id=working_template.metadata.template_id,
            template_version=working_template.metadata.version,
            corrected=corrected,
            iterations_used=iterations_used,
            final_is_valid=final_semantic.is_valid,
        )

        return working_template, CorrectionLoopResult(
            corrected=corrected,
            iterations_used=iterations_used,
            warnings=warnings,
        )

    def _apply_deterministic_fixes(
        self,
        template_definition: TemplateDefinition,
        warnings: list[str],
    ) -> bool:
        """
        Apply deterministic safe fixes.

        Fixes in current phase:
        - restore missing retrieval bindings,
        - downgrade unsupported auto-assigned diagram strategy,
        - repair prompt key if it still points at a diagram prompt after downgrade.
        """
        changed = False

        for section in template_definition.sections:
            if section.retrieval is None:
                section.retrieval = RetrievalBinding(
                    profile_name=self._default_retrieval_profile_name,
                    section_heading=section.title,
                    section_intent=section.title,
                    semantic_role=self._infer_semantic_role(section.title),
                    filters={},
                )
                warnings.append(
                    f"Added default retrieval binding to compiled section `{section.section_id}`."
                )
                changed = True

            if section.generation_strategy == GenerationStrategy.DIAGRAM_PLANTUML:
                replacement_strategy = self._infer_safe_strategy(section.title)
                section.generation_strategy = replacement_strategy
                section.prompt = PromptReference(
                    prompt_key=self._build_prompt_key(section.section_id, section.title),
                    slot_keys=[
                        "source_evidence",
                        "exemplar_evidence",
                        "guideline_evidence",
                        "rolling_context",
                    ],
                    slots_required=["source_evidence"],
                    slots_optional=["exemplar_evidence", "guideline_evidence", "rolling_context"],
                )
                warnings.append(
                    f"Replaced unsupported auto-assigned diagram strategy in section "
                    f"`{section.section_id}` with `{replacement_strategy.value}`."
                )
                changed = True

        return changed

    def _apply_ai_corrections(
        self,
        template_definition: TemplateDefinition,
        *,
        semantic_errors: list[str],
        warnings: list[str],
    ) -> bool:
        """
        Apply optional SK-backed correction suggestions.

        Expected response shape:
        {
          "sections": [
            {
              "section_id": "sec_x",
              "generation_strategy": "summarize_text",
              "prompt_key": "generation/default",
              "retrieval_profile_name": "default_profile"
            }
          ]
        }
        """
        prompt_payload = self._read_yaml_file(self._prompt_path)
        prompt_template = self._extract_prompt_template(prompt_payload, prompt_path=self._prompt_path)
        execution_hints = self._extract_execution_hints(prompt_payload, prompt_path=self._prompt_path)

        response = self._sk_adapter.invoke_structured(  # type: ignore[union-attr]
            prompt_template=prompt_template,
            input_variables={
                "template_definition": template_definition.model_dump(mode="json"),
                "semantic_errors": semantic_errors,
            },
            execution_hints=execution_hints,
        )

        if not isinstance(response, dict):
            warnings.append("Ignored correction response because it was not a mapping/object.")
            return False

        raw_sections = response.get("sections", [])
        if not isinstance(raw_sections, list):
            warnings.append("Ignored correction response because `sections` was not a list.")
            return False

        section_by_id = {section.section_id: section for section in template_definition.sections}
        changed = False

        for item in raw_sections:
            if not isinstance(item, dict):
                warnings.append("Ignored invalid correction entry because it was not a mapping/object.")
                continue

            section_id = item.get("section_id")
            if not isinstance(section_id, str) or section_id not in section_by_id:
                warnings.append("Ignored correction entry with missing or unknown `section_id`.")
                continue

            section = section_by_id[section_id]

            generation_strategy_value = item.get("generation_strategy")
            if isinstance(generation_strategy_value, str) and generation_strategy_value.strip():
                try:
                    proposed_strategy = GenerationStrategy(generation_strategy_value.strip())
                except ValueError:
                    warnings.append(
                        f"Ignored unknown generation strategy suggestion for section `{section_id}`."
                    )
                else:
                    if proposed_strategy == GenerationStrategy.DIAGRAM_PLANTUML:
                        warnings.append(
                            f"Ignored diagram strategy suggestion for section `{section_id}` "
                            "because diagrams are not auto-enabled in the current sprint."
                        )
                    else:
                        section.generation_strategy = proposed_strategy
                        changed = True

            prompt_key = item.get("prompt_key")
            if isinstance(prompt_key, str) and prompt_key.strip():
                section.prompt = PromptReference(
                    prompt_key=prompt_key.strip(),
                    slot_keys=[
                        "source_evidence",
                        "exemplar_evidence",
                        "guideline_evidence",
                        "rolling_context",
                    ],
                    slots_required=["source_evidence"],
                    slots_optional=["exemplar_evidence", "guideline_evidence", "rolling_context"],
                )
                changed = True

            retrieval_profile_name = item.get("retrieval_profile_name")
            if isinstance(retrieval_profile_name, str) and retrieval_profile_name.strip():
                if section.retrieval is None:
                    section.retrieval = RetrievalBinding(
                        profile_name=retrieval_profile_name.strip(),
                        section_heading=section.title,
                        section_intent=section.title,
                        semantic_role=self._infer_semantic_role(section.title),
                        filters={},
                    )
                    changed = True

        return changed

    def _infer_safe_strategy(self, title: str) -> GenerationStrategy:
        """
        Infer a safe fallback strategy that never returns diagram_plantuml.
        """
        normalized = self._header_normalizer.normalize(title)

        if any(token in normalized for token in ("table", "matrix", "mapping", "api", "data model")):
            return GenerationStrategy.GENERATE_TABLE

        return GenerationStrategy.SUMMARIZE_TEXT

    def _build_prompt_key(self, section_id: str, title: str) -> str:
        """
        Build a safe prompt key after deterministic correction.
        """
        normalized_id = section_id
        if normalized_id.startswith("sec_"):
            normalized_id = normalized_id[4:]
        if not normalized_id:
            normalized_id = self._header_normalizer.slugify(title) or "default"
        return f"generation/{normalized_id}"

    def _infer_semantic_role(self, title: str) -> str:
        """
        Infer a simple semantic role for fallback retrieval bindings.
        """
        normalized = self._header_normalizer.normalize(title)

        if any(token in normalized for token in ("architecture", "component", "overview")):
            return "architecture"
        if any(token in normalized for token in ("requirement", "scope", "acceptance")):
            return "requirements"
        if any(token in normalized for token in ("process", "workflow", "sequence", "flow")):
            return "process"
        if any(token in normalized for token in ("risk", "assumption", "constraint")):
            return "governance"

        return "general"

    @staticmethod
    def _read_yaml_file(path: Path) -> dict[str, Any]:
        """Read and parse a YAML object file."""
        if not path.exists():
            raise FileNotFoundError(f"Correction-loop prompt YAML not found: {path}")

        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in correction-loop prompt: {path}") from exc

        if not isinstance(payload, dict):
            raise ValueError(f"Correction-loop prompt YAML must contain a mapping/object root: {path}")

        return payload

    def _extract_prompt_template(self, payload: dict[str, Any], *, prompt_path: Path) -> str:
        """Extract prompt body from YAML."""
        for key in self._PROMPT_BODY_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        raise ValueError(
            f"Correction-loop prompt YAML must define one of {self._PROMPT_BODY_KEYS}: {prompt_path}"
        )

    def _extract_execution_hints(
        self,
        payload: dict[str, Any],
        *,
        prompt_path: Path,
    ) -> dict[str, Any]:
        """
        Extract GPT-5-compatible execution hints and forbid unsupported keys.
        """
        raw_hints = payload.get("execution_hints", {})
        if raw_hints is None:
            raw_hints = {}

        if not isinstance(raw_hints, dict):
            raise ValueError(f"`execution_hints` must be a mapping in correction-loop prompt: {prompt_path}")

        forbidden_keys = set(raw_hints).intersection(self._FORBIDDEN_EXECUTION_HINT_KEYS)
        if forbidden_keys:
            raise ValueError(
                "Correction-loop prompt contains unsupported execution hint key(s): "
                f"{sorted(forbidden_keys)} in {prompt_path}"
            )

        unknown_keys = set(raw_hints) - self._ALLOWED_EXECUTION_HINT_KEYS
        if unknown_keys:
            raise ValueError(
                f"Unknown execution_hints key(s) in correction-loop prompt: {sorted(unknown_keys)} in {prompt_path}"
            )

        response_token_budget = raw_hints.get("response_token_budget")
        if response_token_budget is not None:
            if not isinstance(response_token_budget, int) or response_token_budget <= 0:
                raise ValueError(
                    f"`response_token_budget` must be a positive integer in correction-loop prompt: {prompt_path}"
                )

        return {
            key: value
            for key, value in {
                "model_preference": raw_hints.get("model_preference"),
                "reasoning_effort": raw_hints.get("reasoning_effort"),
                "verbosity": raw_hints.get("verbosity"),
                "response_token_budget": response_token_budget,
            }.items()
            if value is not None
        }

    def _log_info(self, event_name: str, **payload: object) -> None:
        """Emit a lightweight structured-ish log entry."""
        self._logger.info("%s | %s", event_name, payload)