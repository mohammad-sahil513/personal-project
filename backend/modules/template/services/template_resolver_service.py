"""
Template resolver service.

This service converts a validated TemplateDefinition into a list of
ResolvedSection objects suitable for downstream generation.

Phase 4 responsibilities:
- dependency-aware ordering,
- default + section grounding merge,
- retrieval override merge,
- evidence_confidence_floor -> min_confidence mapping,
- inline retrieval plan overlay,
- runtime warning propagation for placeholder/conditional cases.

Out of scope:
- prompt family selection logic beyond carrying prompt metadata,
- retrieval execution,
- generation execution,
- compiler/layout execution.
"""

from __future__ import annotations

import copy
import logging

from ..contracts.section_contracts import ResolvedSection, TemplateSection
from ..contracts.template_contracts import (
    GroundingPolicy,
    RetrievalOverrideConfig,
    TemplateDefinition,
)
from ..models.template_config import REQUIREMENT_IDS_RUNTIME_NOTE, is_unimplemented_strategy
from ..services.dependency_sorter_service import DependencySorterService


class TemplateResolverService:
    """
    Resolve template sections into execution-ready section metadata.

    Design note:
    The resolver does not execute retrieval. It only prepares aligned section
    configuration that downstream generation can consume.
    """

    def __init__(
        self,
        *,
        dependency_sorter: DependencySorterService | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._dependency_sorter = dependency_sorter or DependencySorterService()
        self._logger = logger or logging.getLogger(__name__)

    def resolve_template(
        self,
        template_definition: TemplateDefinition,
        *,
        requirement_ids_filter_supported: bool = False,
    ) -> list[ResolvedSection]:
        """
        Resolve a template definition into dependency-ordered sections.

        Args:
            template_definition: Typed template artifact to resolve.
            requirement_ids_filter_supported:
                Whether the currently deployed runtime/index schema supports
                direct filtering on `requirement_ids`.

        Returns:
            Ordered list of ResolvedSection objects.
        """
        self._log_info(
            "template_resolution_start",
            template_id=template_definition.metadata.template_id,
            template_version=template_definition.metadata.version,
            template_type=template_definition.metadata.template_type.value,
            section_count=len(template_definition.sections),
            requirement_ids_filter_supported=requirement_ids_filter_supported,
        )

        ordered_sections = self._dependency_sorter.sort_sections(template_definition.sections)
        resolved_sections: list[ResolvedSection] = []

        for execution_order, section in enumerate(ordered_sections):
            resolved_sections.append(
                self._resolve_section(
                    section=section,
                    execution_order=execution_order,
                    default_grounding_policy=template_definition.default_grounding_policy,
                    requirement_ids_filter_supported=requirement_ids_filter_supported,
                )
            )

        self._log_info(
            "template_resolution_completed",
            template_id=template_definition.metadata.template_id,
            template_version=template_definition.metadata.version,
            resolved_section_count=len(resolved_sections),
        )
        return resolved_sections

    # ------------------------------------------------------------------
    # Section resolution helpers
    # ------------------------------------------------------------------

    def _resolve_section(
        self,
        *,
        section: TemplateSection,
        execution_order: int,
        default_grounding_policy: GroundingPolicy,
        requirement_ids_filter_supported: bool,
    ) -> ResolvedSection:
        """Resolve one template section into its downstream handoff shape."""
        merged_grounding_policy = self._merge_grounding_policy(
            default_policy=default_grounding_policy,
            section_policy=section.grounding_policy,
        )

        merged_retrieval_overrides = None
        inline_retrieval_plan = None
        retrieval_profile_name = None

        if section.retrieval is not None:
            merged_retrieval_overrides = self._merge_retrieval_overrides(
                section_overrides=section.retrieval.overrides,
                merged_grounding_policy=merged_grounding_policy,
            )
            inline_retrieval_plan = self._build_resolved_inline_plan(
                inline_plan=section.retrieval.inline_plan,
                merged_overrides=merged_retrieval_overrides,
            )
            retrieval_profile_name = section.retrieval.profile_name

        runtime_warnings = self._build_runtime_warnings(
            section=section,
            requirement_ids_filter_supported=requirement_ids_filter_supported,
        )

        return ResolvedSection(
            section_id=section.section_id,
            title=section.title,
            execution_order=execution_order,
            generation_strategy=section.generation_strategy,
            prompt_key=section.prompt.prompt_key,
            slots_required=list(section.prompt.slots_required),
            slots_optional=list(section.prompt.slots_optional),
            retrieval_profile_name=retrieval_profile_name,
            inline_retrieval_plan=inline_retrieval_plan,
            merged_retrieval_overrides=merged_retrieval_overrides,
            grounding_policy=merged_grounding_policy,
            validation_rules=section.validation_rules,
            dependencies=list(section.dependencies),
            no_evidence_policy=section.no_evidence_policy,
            runtime_warnings=runtime_warnings,
        )

    @staticmethod
    def _merge_grounding_policy(
        *,
        default_policy: GroundingPolicy,
        section_policy: GroundingPolicy | None,
    ) -> GroundingPolicy:
        """
        Merge section grounding into template defaults.

        Important behavior:
        - template defaults establish the baseline,
        - section policy overrides only fields explicitly supplied on the section.
        """
        merged_payload = default_policy.model_dump(mode="python")

        if section_policy is not None:
            merged_payload.update(section_policy.model_dump(exclude_unset=True, mode="python"))

        return GroundingPolicy.model_validate(merged_payload)

    @staticmethod
    def _merge_retrieval_overrides(
        *,
        section_overrides: RetrievalOverrideConfig | None,
        merged_grounding_policy: GroundingPolicy,
    ) -> RetrievalOverrideConfig:
        """
        Merge retrieval overrides and apply evidence floor mapping.

        Resolution rule:
        - explicit `min_confidence` in section overrides wins,
        - otherwise `evidence_confidence_floor` maps into retrieval `min_confidence`.
        """
        payload = (
            section_overrides.model_dump(exclude_none=True, mode="python")
            if section_overrides is not None
            else {}
        )

        if "min_confidence" not in payload:
            payload["min_confidence"] = merged_grounding_policy.evidence_confidence_floor

        return RetrievalOverrideConfig.model_validate(payload)

    @staticmethod
    def _build_resolved_inline_plan(
        *,
        inline_plan: dict[str, object] | None,
        merged_overrides: RetrievalOverrideConfig | None,
    ) -> dict[str, object] | None:
        """
        Build the final inline retrieval plan for downstream execution.

        Merge order:
        1. start with the declared inline plan,
        2. overlay resolved override values,
        3. preserve distinct `top_k` vs `final_output_top_k` keys.
        """
        if inline_plan is None:
            return None

        resolved_plan = copy.deepcopy(inline_plan)

        if merged_overrides is not None:
            resolved_plan.update(merged_overrides.model_dump(exclude_none=True, mode="python"))

        return resolved_plan

    @staticmethod
    def _build_runtime_warnings(
        *,
        section: TemplateSection,
        requirement_ids_filter_supported: bool,
    ) -> list[str]:
        """
        Build runtime-facing warnings that downstream orchestration can surface.

        These warnings complement (but do not replace) validator warnings.
        """
        warnings: list[str] = []

        if is_unimplemented_strategy(section.generation_strategy.value):
            warnings.append(
                f"Strategy `{section.generation_strategy.value}` is contract-valid "
                "but not enabled in the current runtime scope."
            )

        if (
            section.retrieval is not None
            and "requirement_ids" in section.retrieval.filters
            and not requirement_ids_filter_supported
        ):
            warnings.append(REQUIREMENT_IDS_RUNTIME_NOTE)

        return warnings

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _log_info(self, event_name: str, **payload: object) -> None:
        """
        Emit a lightweight structured-ish log entry.

        Later phases can route these calls into the shared observability module
        without changing the resolver business logic.
        """
        self._logger.info("%s | %s", event_name, payload)