"""
Prompt selector service.

This service is the Template-side source of truth for:
- resolving the correct YAML prompt file for a section,
- validating prompt metadata against the resolved slot contract,
- providing explicit empty-slot and low-evidence instructions,
- returning GPT-5 / GPT-5-mini compatible execution hints without relying on
  temperature or max_tokens.

Important boundary:
- This service selects and validates prompt artifacts.
- It does NOT assemble the final runtime prompt payload.
- It does NOT execute the model.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..contracts.section_contracts import ResolvedSection
from ..models.template_enums import GenerationStrategy


@dataclass(frozen=True, slots=True)
class PromptExecutionHints:
    """
    Model-execution hints compatible with GPT-5 / GPT-5-mini style usage.

    Notes:
    - `temperature` and `max_tokens` are intentionally not supported here.
    - `response_token_budget` is a neutral hint that downstream code can map
      into the correct model/client-specific output token control.
    """

    model_preference: str | None = None
    reasoning_effort: str | None = None
    verbosity: str | None = None
    response_token_budget: int | None = None


@dataclass(frozen=True, slots=True)
class SelectedPrompt:
    """
    Result of prompt selection for one resolved section.

    This object is intentionally downstream-friendly: it carries the prompt path,
    normalized prompt body, slot contract, execution hints, and runtime guidance
    needed by the generation layer without assembling the final model payload.
    """

    section_id: str
    generation_strategy: str
    prompt_key: str
    prompt_family: str
    prompt_name: str
    prompt_path: Path
    prompt_template: str
    slots_required: list[str]
    slots_optional: list[str]
    empty_slot_instructions: dict[str, str]
    no_evidence_instruction: str
    low_source_evidence_instruction: str
    execution_hints: PromptExecutionHints
    runtime_warnings: list[str] = field(default_factory=list)


class PromptSelectorService:
    """
    Select and validate prompt YAML files for resolved sections.

    YAML prompt expectations:
    - Prompts are stored under `prompts/generation/<family>/<name>.yaml`
    - Each YAML file may define:
        - `prompt_template` (required; alias: `template`)
        - `slot_contract` (optional)
        - `empty_slot_instructions` (optional)
        - `no_evidence_instruction` (optional)
        - `low_source_evidence_instruction` (optional)
        - `execution_hints` (optional)
    - `temperature` and `max_tokens` are intentionally forbidden in
      `execution_hints` for this project.
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
        project_root: str | Path | None = None,
        prompts_root: str | Path | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        resolved_project_root = (
            Path(project_root).resolve()
            if project_root is not None
            else Path(__file__).resolve().parents[4]
        )

        self._project_root = resolved_project_root
        self._prompts_root = (
            Path(prompts_root).resolve()
            if prompts_root is not None
            else resolved_project_root / "prompts"
        )
        self._logger = logger or logging.getLogger(__name__)

    @property
    def prompts_root(self) -> Path:
        """Return the resolved prompt-root directory."""
        return self._prompts_root

    def select_prompt_for_section(self, resolved_section: ResolvedSection) -> SelectedPrompt:
        """
        Select and validate a YAML prompt for one resolved section.

        Resolution behavior:
        1. infer prompt family from generation strategy,
        2. resolve prompt name from `prompt_key`,
        3. load `<family>/<prompt_name>.yaml`,
        4. fall back to `<family>/default.yaml` if the specific file is absent,
        5. validate slot contract + execution hints.

        Args:
            resolved_section: Section metadata produced by the resolver layer.

        Returns:
            SelectedPrompt with normalized metadata.
        """
        prompt_family = self._determine_prompt_family(resolved_section.generation_strategy)
        prompt_name = self._normalize_prompt_name(resolved_section.prompt_key)
        prompt_path = self._resolve_prompt_path(prompt_family=prompt_family, prompt_name=prompt_name)

        payload = self._read_yaml_file(prompt_path)
        prompt_template = self._extract_prompt_template(payload, prompt_path=prompt_path)
        self._validate_slot_contract(payload=payload, resolved_section=resolved_section, prompt_path=prompt_path)
        execution_hints = self._extract_execution_hints(payload=payload, prompt_path=prompt_path)

        selected_prompt = SelectedPrompt(
            section_id=resolved_section.section_id,
            generation_strategy=resolved_section.generation_strategy.value,
            prompt_key=resolved_section.prompt_key,
            prompt_family=prompt_family,
            prompt_name=prompt_path.stem,
            prompt_path=prompt_path,
            prompt_template=prompt_template,
            slots_required=list(resolved_section.slots_required),
            slots_optional=list(resolved_section.slots_optional),
            empty_slot_instructions=self._build_empty_slot_instructions(payload=payload),
            no_evidence_instruction=self._build_no_evidence_instruction(payload=payload),
            low_source_evidence_instruction=self._build_low_source_evidence_instruction(payload=payload),
            execution_hints=execution_hints,
            runtime_warnings=list(resolved_section.runtime_warnings),
        )

        self._log_info(
            "prompt_selection_completed",
            section_id=resolved_section.section_id,
            prompt_family=selected_prompt.prompt_family,
            prompt_name=selected_prompt.prompt_name,
            prompt_path=str(selected_prompt.prompt_path),
        )
        return selected_prompt

    def select_prompts(self, resolved_sections: list[ResolvedSection]) -> list[SelectedPrompt]:
        """
        Select prompts for all resolved sections in order.

        Args:
            resolved_sections: Dependency-ordered resolved sections.

        Returns:
            List of SelectedPrompt entries in the same order.
        """
        return [self.select_prompt_for_section(section) for section in resolved_sections]

    # ------------------------------------------------------------------
    # Prompt path resolution
    # ------------------------------------------------------------------

    def _determine_prompt_family(self, generation_strategy: GenerationStrategy) -> str:
        """Map generation strategy to generation prompt-family folder."""
        strategy_to_family = {
            GenerationStrategy.SUMMARIZE_TEXT: "summarize_text",
            GenerationStrategy.GENERATE_TABLE: "generate_table",
            GenerationStrategy.DIAGRAM_PLANTUML: "diagram_plantuml",
        }

        try:
            return strategy_to_family[generation_strategy]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported generation strategy for prompt selection: {generation_strategy.value}"
            ) from exc

    @staticmethod
    def _normalize_prompt_name(prompt_key: str) -> str:
        """
        Normalize a logical prompt key into a YAML filename stem.

        Examples:
        - "generation/default" -> "default"
        - "generation/system_overview" -> "system_overview"
        - "executive_summary" -> "executive_summary"
        """
        normalized = prompt_key.strip()
        if not normalized:
            raise ValueError("Prompt key must not be empty.")

        if "/" in normalized:
            normalized = normalized.split("/")[-1]

        if normalized.endswith(".yaml"):
            normalized = normalized[:-5]

        if not normalized:
            raise ValueError("Prompt key did not resolve to a valid YAML prompt name.")

        return normalized

    def _resolve_prompt_path(self, *, prompt_family: str, prompt_name: str) -> Path:
        """
        Resolve a prompt YAML path, falling back to family default.yaml.

        Raises:
            FileNotFoundError: If neither the requested file nor default.yaml exists.
        """
        family_dir = self._prompts_root / "generation" / prompt_family
        requested_path = family_dir / f"{prompt_name}.yaml"

        if requested_path.exists():
            return requested_path.resolve()

        fallback_path = family_dir / "default.yaml"
        if fallback_path.exists():
            return fallback_path.resolve()

        raise FileNotFoundError(
            f"Prompt YAML not found for family `{prompt_family}`. "
            f"Tried `{requested_path}` and `{fallback_path}`."
        )

    # ------------------------------------------------------------------
    # YAML loading and validation
    # ------------------------------------------------------------------

    @staticmethod
    def _read_yaml_file(path: Path) -> dict[str, Any]:
        """Read and parse a YAML object file."""
        try:
            with path.open("r", encoding="utf-8") as handle:
                payload = yaml.safe_load(handle)
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid YAML in prompt file: {path}") from exc

        if not isinstance(payload, dict):
            raise ValueError(f"Prompt YAML must contain a mapping/object root: {path}")

        return payload

    def _extract_prompt_template(self, payload: dict[str, Any], *, prompt_path: Path) -> str:
        """
        Extract the main prompt body from YAML.

        Supported keys:
        - prompt_template
        - template
        """
        for key in self._PROMPT_BODY_KEYS:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        raise ValueError(
            f"Prompt YAML must define one of {self._PROMPT_BODY_KEYS}: {prompt_path}"
        )

    def _validate_slot_contract(
        self,
        *,
        payload: dict[str, Any],
        resolved_section: ResolvedSection,
        prompt_path: Path,
    ) -> None:
        """
        Validate optional YAML slot contract against the resolved section contract.

        Rule:
        - Template resolver remains the source of truth for slot requirements.
        - YAML may document the same contract, but must not contradict it.
        """
        raw_slot_contract = payload.get("slot_contract")
        if raw_slot_contract is None:
            return

        if not isinstance(raw_slot_contract, dict):
            raise ValueError(f"`slot_contract` must be a mapping in prompt YAML: {prompt_path}")

        yaml_required = raw_slot_contract.get("slots_required", [])
        yaml_optional = raw_slot_contract.get("slots_optional", [])

        if not isinstance(yaml_required, list) or not all(isinstance(item, str) for item in yaml_required):
            raise ValueError(f"`slot_contract.slots_required` must be a list[str]: {prompt_path}")

        if not isinstance(yaml_optional, list) or not all(isinstance(item, str) for item in yaml_optional):
            raise ValueError(f"`slot_contract.slots_optional` must be a list[str]: {prompt_path}")

        if set(yaml_required) != set(resolved_section.slots_required):
            raise ValueError(
                "Prompt YAML required slots do not match the resolved section contract "
                f"for section `{resolved_section.section_id}`: {prompt_path}"
            )

        if set(yaml_optional) != set(resolved_section.slots_optional):
            raise ValueError(
                "Prompt YAML optional slots do not match the resolved section contract "
                f"for section `{resolved_section.section_id}`: {prompt_path}"
            )

    def _extract_execution_hints(
        self,
        *,
        payload: dict[str, Any],
        prompt_path: Path,
    ) -> PromptExecutionHints:
        """
        Extract GPT-5 compatible execution hints from YAML.

        Forbidden keys:
        - temperature
        - max_tokens

        Supported alternatives:
        - model_preference
        - reasoning_effort
        - verbosity
        - response_token_budget
        """
        raw_hints = payload.get("execution_hints", {})
        if raw_hints is None:
            raw_hints = {}

        if not isinstance(raw_hints, dict):
            raise ValueError(f"`execution_hints` must be a mapping in prompt YAML: {prompt_path}")

        forbidden_keys = set(raw_hints).intersection(self._FORBIDDEN_EXECUTION_HINT_KEYS)
        if forbidden_keys:
            raise ValueError(
                "Prompt YAML execution_hints contains unsupported key(s) for this project: "
                f"{sorted(forbidden_keys)} in {prompt_path}"
            )

        unknown_keys = set(raw_hints) - self._ALLOWED_EXECUTION_HINT_KEYS
        if unknown_keys:
            raise ValueError(
                f"Unknown execution_hints key(s) in prompt YAML: {sorted(unknown_keys)} in {prompt_path}"
            )

        response_token_budget = raw_hints.get("response_token_budget")
        if response_token_budget is not None:
            if not isinstance(response_token_budget, int) or response_token_budget <= 0:
                raise ValueError(
                    f"`response_token_budget` must be a positive integer in prompt YAML: {prompt_path}"
                )

        return PromptExecutionHints(
            model_preference=self._optional_string(raw_hints.get("model_preference"), field_name="model_preference", prompt_path=prompt_path),
            reasoning_effort=self._optional_string(raw_hints.get("reasoning_effort"), field_name="reasoning_effort", prompt_path=prompt_path),
            verbosity=self._optional_string(raw_hints.get("verbosity"), field_name="verbosity", prompt_path=prompt_path),
            response_token_budget=response_token_budget,
        )

    @staticmethod
    def _optional_string(value: Any, *, field_name: str, prompt_path: Path) -> str | None:
        """Validate an optional non-empty string field from YAML."""
        if value is None:
            return None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"`{field_name}` must be a non-empty string in prompt YAML: {prompt_path}")
        return value.strip()

    # ------------------------------------------------------------------
    # Instruction builders
    # ------------------------------------------------------------------

    @staticmethod
    def _build_empty_slot_instructions(payload: dict[str, Any]) -> dict[str, str]:
        """
        Build explicit instructions for optional empty slots.

        Defaults align with the final Template plan:
        - exemplar empty -> use standard SDLC structure/formatting
        - guideline empty -> use general best-practice constraints
        - rolling context empty -> continue without continuity claims
        """
        defaults = {
            "exemplar_evidence": (
                "If exemplar evidence is empty, use standard SDLC structure and formatting conventions."
            ),
            "guideline_evidence": (
                "If guideline evidence is empty, use general best-practice constraints without inventing policy text."
            ),
            "rolling_context": (
                "If rolling context is empty, proceed without continuity assumptions from prior sections."
            ),
        }

        raw = payload.get("empty_slot_instructions", {})
        if raw is None:
            raw = {}

        if not isinstance(raw, dict):
            raise ValueError("`empty_slot_instructions` must be a mapping in prompt YAML.")

        instructions = dict(defaults)
        for key, value in raw.items():
            if not isinstance(key, str) or not isinstance(value, str) or not value.strip():
                raise ValueError("`empty_slot_instructions` entries must be string-to-string values.")
            instructions[key] = value.strip()

        return instructions

    @staticmethod
    def _build_no_evidence_instruction(payload: dict[str, Any]) -> str:
        """
        Build the no-evidence instruction.

        This is intentionally explicit because SOURCE evidence must not be treated
        as optional during downstream prompt assembly.
        """
        raw = payload.get("no_evidence_instruction")
        if raw is None:
            return (
                "If source evidence is empty, do not continue silently; apply the section no_evidence_policy."
            )

        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("`no_evidence_instruction` must be a non-empty string when provided.")

        return raw.strip()

    @staticmethod
    def _build_low_source_evidence_instruction(payload: dict[str, Any]) -> str:
        """
        Build the low-SOURCE-evidence instruction.

        The default aligns with the locked rule that sections with fewer than two
        SOURCE facts should be marked degraded and require review.
        """
        raw = payload.get("low_source_evidence_instruction")
        if raw is None:
            return (
                "If SOURCE evidence has fewer than 2 facts, mark the section as low-evidence, "
                "set the outcome to degraded, and require manual review."
            )

        if not isinstance(raw, str) or not raw.strip():
            raise ValueError(
                "`low_source_evidence_instruction` must be a non-empty string when provided."
            )

        return raw.strip()

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_info(self, event_name: str, **payload: object) -> None:
        """
        Emit a lightweight structured-ish log entry.

        Later phases can route this through the shared observability module
        without changing prompt selection logic.
        """
        self._logger.info("%s | %s", event_name, payload)
