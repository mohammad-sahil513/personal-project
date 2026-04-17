"""
Semantic validator for compiled custom templates.

This validator sits after deterministic compile/default injection and checks:
- base Template validation rules,
- compiler-specific constraints,
- current-sprint diagram guardrails.

It intentionally produces a compiler-focused SemanticValidationResult rather
than mutating the template.
"""

from __future__ import annotations

import logging

from ..contracts.compiler_contracts import SemanticValidationResult
from ..contracts.template_contracts import TemplateDefinition
from ..models.template_enums import GenerationStrategy, TemplateType
from ..services.template_validator_service import TemplateValidatorService


class SemanticValidator:
    """
    Validate compiled custom TemplateDefinition artifacts semantically.
    """

    def __init__(
        self,
        *,
        template_validator: TemplateValidatorService | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._template_validator = template_validator or TemplateValidatorService()
        self._logger = logger or logging.getLogger(__name__)

    def validate_compiled_template(
        self,
        template_definition: TemplateDefinition,
        *,
        requirement_ids_filter_supported: bool = False,
    ) -> SemanticValidationResult:
        """
        Validate a compiled custom template for semantic correctness.

        Returns:
            SemanticValidationResult with aggregated errors and warnings.
        """
        errors: list[str] = []
        warnings: list[str] = []

        self._log_info(
            "compiler_semantic_validation_start",
            template_id=template_definition.metadata.template_id,
            template_version=template_definition.metadata.version,
            template_type=template_definition.metadata.template_type.value,
        )

        if template_definition.metadata.template_type != TemplateType.CUSTOM:
            warnings.append(
                "Compiled template validation was run for a non-custom template definition."
            )

        template_validation = self._template_validator.validate_template(
            template_definition,
            requirement_ids_filter_supported=requirement_ids_filter_supported,
        )

        errors.extend(issue.message for issue in template_validation.issues if issue.severity.value == "error")
        warnings.extend(issue.message for issue in template_validation.issues if issue.severity.value == "warning")

        for section in template_definition.sections:
            if section.retrieval is None:
                errors.append(
                    f"Compiled section `{section.section_id}` is missing a retrieval binding."
                )

            if section.generation_strategy == GenerationStrategy.DIAGRAM_PLANTUML:
                errors.append(
                    f"Compiled section `{section.section_id}` auto-assigned "
                    "`diagram_plantuml`, which is not allowed in the current sprint."
                )

        result = SemanticValidationResult(
            is_valid=(len(errors) == 0),
            errors=errors,
            warnings=warnings,
        )

        self._log_info(
            "compiler_semantic_validation_completed",
            template_id=template_definition.metadata.template_id,
            template_version=template_definition.metadata.version,
            is_valid=result.is_valid,
            error_count=len(result.errors),
            warning_count=len(result.warnings),
        )
        return result

    def _log_info(self, event_name: str, **payload: object) -> None:
        """Emit a lightweight structured-ish log entry."""
        self._logger.info("%s | %s", event_name, payload)