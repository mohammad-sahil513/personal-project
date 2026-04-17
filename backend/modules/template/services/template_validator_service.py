"""
Template validation service.

This service performs semantic and policy validation on top of the typed
Template contracts introduced in earlier phases.

Why this exists:
- Pydantic contracts catch structural/schema issues.
- This service catches runtime-policy issues that depend on template type,
  retrieval alignment, and current deployment constraints.

Phase 3 scope:
- filter-key validation,
- standard vs custom override validation,
- placeholder strategy warnings,
- requirement_ids runtime-conditional warnings,
- dependency-reference validation.

Out of scope for this phase:
- retrieval-plan resolution,
- dependency sorting,
- prompt selection,
- compiler/layout execution.
"""

from __future__ import annotations

import logging

from ..contracts.section_contracts import RetrievalBinding, TemplateSection
from ..contracts.template_contracts import RetrievalOverrideConfig, TemplateDefinition
from ..contracts.validation_contracts import TemplateValidationResult
from ..models.template_config import (
    REQUIREMENT_IDS_RUNTIME_NOTE,
    is_allowed_filter_key,
    is_allowed_override_key,
    is_removed_filter_key,
    is_unimplemented_strategy,
)
from ..models.template_enums import TemplateType, TemplateValidationCode


class TemplateValidatorService:
    """
    Semantic/policy validator for template definitions.

    This validator is intentionally deterministic and side-effect free. It does
    not modify templates; it only reports issues through TemplateValidationResult.
    """

    def __init__(self, *, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger(__name__)

    def validate_template(
        self,
        template_definition: TemplateDefinition,
        *,
        requirement_ids_filter_supported: bool = False,
    ) -> TemplateValidationResult:
        """
        Validate a template definition against the aligned template rules.

        Args:
            template_definition: Parsed template artifact to validate.
            requirement_ids_filter_supported:
                Whether the currently deployed runtime/index schema supports
                direct filtering on `requirement_ids`.

        Returns:
            TemplateValidationResult containing typed errors and warnings.
        """
        result = TemplateValidationResult()
        template_type = template_definition.metadata.template_type
        known_section_ids = {section.section_id for section in template_definition.sections}

        self._log_info(
            "template_validation_start",
            template_id=template_definition.metadata.template_id,
            template_version=template_definition.metadata.version,
            template_type=template_type.value,
            requirement_ids_filter_supported=requirement_ids_filter_supported,
        )

        for index, section in enumerate(template_definition.sections):
            field_prefix = f"sections[{index}]"
            self._validate_section(
                section=section,
                field_prefix=field_prefix,
                known_section_ids=known_section_ids,
                template_type=template_type,
                result=result,
                requirement_ids_filter_supported=requirement_ids_filter_supported,
            )

        self._log_info(
            "template_validation_completed",
            template_id=template_definition.metadata.template_id,
            template_version=template_definition.metadata.version,
            template_type=template_type.value,
            error_count=result.error_count,
            warning_count=result.warning_count,
            is_valid=result.is_valid,
        )
        return result

    # ------------------------------------------------------------------
    # Section-level validation helpers
    # ------------------------------------------------------------------

    def _validate_section(
        self,
        *,
        section: TemplateSection,
        field_prefix: str,
        known_section_ids: set[str],
        template_type: TemplateType,
        result: TemplateValidationResult,
        requirement_ids_filter_supported: bool,
    ) -> None:
        """Validate one template section."""
        self._validate_generation_strategy(
            section=section,
            field_prefix=field_prefix,
            result=result,
        )
        self._validate_dependencies(
            section=section,
            field_prefix=field_prefix,
            known_section_ids=known_section_ids,
            result=result,
        )

        if section.retrieval is not None:
            self._validate_retrieval_binding(
                retrieval=section.retrieval,
                field_prefix=f"{field_prefix}.retrieval",
                template_type=template_type,
                result=result,
                requirement_ids_filter_supported=requirement_ids_filter_supported,
            )

    def _validate_generation_strategy(
        self,
        *,
        section: TemplateSection,
        field_prefix: str,
        result: TemplateValidationResult,
    ) -> None:
        """
        Warn for placeholder-compatible but runtime-disabled strategies.

        Current aligned behavior:
        - `diagram_plantuml` is contract-valid,
        - but remains warning-only for the current downstream-compatible sprint.
        """
        strategy_value = section.generation_strategy.value
        if is_unimplemented_strategy(strategy_value):
            result.add_warning(
                code=TemplateValidationCode.UNIMPLEMENTED_STRATEGY,
                message=(
                    f"Strategy `{strategy_value}` is contract-valid but not enabled "
                    "in the current runtime scope."
                ),
                field_path=f"{field_prefix}.generation_strategy",
                context={"strategy": strategy_value},
            )

    def _validate_dependencies(
        self,
        *,
        section: TemplateSection,
        field_prefix: str,
        known_section_ids: set[str],
        result: TemplateValidationResult,
    ) -> None:
        """Ensure all declared dependencies reference existing sections."""
        for dependency in section.dependencies:
            if dependency not in known_section_ids:
                result.add_error(
                    code=TemplateValidationCode.INVALID_DEPENDENCY,
                    message=f"Unknown dependency reference: `{dependency}`.",
                    field_path=f"{field_prefix}.dependencies",
                    context={"missing_dependency": dependency},
                )

    # ------------------------------------------------------------------
    # Retrieval validation helpers
    # ------------------------------------------------------------------

    def _validate_retrieval_binding(
        self,
        *,
        retrieval: RetrievalBinding,
        field_prefix: str,
        template_type: TemplateType,
        result: TemplateValidationResult,
        requirement_ids_filter_supported: bool,
    ) -> None:
        """Validate retrieval filters and override policy for a section."""
        self._validate_filter_keys(
            filters=retrieval.filters,
            field_prefix=f"{field_prefix}.filters",
            result=result,
            requirement_ids_filter_supported=requirement_ids_filter_supported,
        )

        if retrieval.overrides is not None:
            self._validate_override_keys(
                overrides=retrieval.overrides,
                field_prefix=f"{field_prefix}.overrides",
                template_type=template_type,
                result=result,
            )

    def _validate_filter_keys(
        self,
        *,
        filters: dict[str, object],
        field_prefix: str,
        result: TemplateValidationResult,
        requirement_ids_filter_supported: bool,
    ) -> None:
        """
        Validate filter keys against the aligned retrieval/index schema.

        Rules:
        - aligned keys are allowed,
        - removed legacy keys are hard errors,
        - unknown keys are hard errors,
        - requirement_ids is contract-valid but may emit a runtime warning.
        """
        for key in filters:
            field_path = f"{field_prefix}.{key}"

            if is_removed_filter_key(key):
                result.add_error(
                    code=TemplateValidationCode.INVALID_FILTER_KEY,
                    message=f"Removed/unsupported filter key: `{key}`.",
                    field_path=field_path,
                    context={"filter_key": key},
                )
                continue

            if not is_allowed_filter_key(key):
                result.add_error(
                    code=TemplateValidationCode.INVALID_FILTER_KEY,
                    message=f"Invalid filter key for aligned retrieval schema: `{key}`.",
                    field_path=field_path,
                    context={"filter_key": key},
                )
                continue

            if key == "requirement_ids" and not requirement_ids_filter_supported:
                result.add_warning(
                    code=TemplateValidationCode.CONDITIONAL_RUNTIME_SUPPORT,
                    message=REQUIREMENT_IDS_RUNTIME_NOTE,
                    field_path=field_path,
                    context={
                        "filter_key": key,
                        "fallback": "has_requirement_id",
                    },
                )

    def _validate_override_keys(
        self,
        *,
        overrides: RetrievalOverrideConfig,
        field_prefix: str,
        template_type: TemplateType,
        result: TemplateValidationResult,
    ) -> None:
        """
        Validate override keys against template-type-specific policy.

        Important distinction:
        - the Pydantic contract limits which keys can exist at all,
        - this service enforces whether those keys are allowed for STANDARD vs CUSTOM.
        """
        is_custom_template = template_type == TemplateType.CUSTOM
        override_payload = overrides.model_dump(exclude_none=True)

        for key in override_payload:
            if is_allowed_override_key(key, is_custom_template=is_custom_template):
                continue

            template_type_label = template_type.value
            result.add_error(
                code=TemplateValidationCode.INVALID_OVERRIDE_KEY,
                message=(
                    f"Override key `{key}` is not allowed for template type "
                    f"`{template_type_label}`."
                ),
                field_path=f"{field_prefix}.{key}",
                context={
                    "override_key": key,
                    "template_type": template_type_label,
                },
            )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_info(self, event_name: str, **payload: object) -> None:
        """
        Emit a lightweight structured-ish log entry.

        Later phases can replace or wrap this logger with the shared
        observability layer without changing validation logic.
        """
        self._logger.info("%s | %s", event_name, payload)