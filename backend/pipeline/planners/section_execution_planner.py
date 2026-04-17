"""
Planner for building normalized section execution plans from resolved template sections.
"""

from __future__ import annotations

from typing import Any

from backend.application.dto.section_plan_dto import SectionPlanDTO, SectionPlanItemDTO
from backend.core.exceptions import ValidationError


DEFAULT_GENERATION_STRATEGY = "summarize_text"
DEFAULT_RETRIEVAL_PROFILE = "default"


class SectionExecutionPlanner:
    """
    Build a normalized section execution plan from resolved template section data.
    """

    def build_plan(
        self,
        *,
        template_id: str,
        resolved_sections: list[dict[str, Any]],
    ) -> SectionPlanDTO:
        if not template_id:
            raise ValidationError(
                message="template_id is required for section planning",
                error_code="SECTION_PLAN_INVALID",
                details={"field": "template_id"},
            )

        if resolved_sections is None:
            raise ValidationError(
                message="resolved_sections is required",
                error_code="SECTION_PLAN_INVALID",
                details={"field": "resolved_sections"},
            )

        normalized_sections = [self._normalize_section(section) for section in resolved_sections]
        normalized_sections.sort(key=lambda item: item.execution_order)

        return SectionPlanDTO(
            template_id=template_id,
            total_sections=len(normalized_sections),
            sections=normalized_sections,
        )

    def _normalize_section(self, section: dict[str, Any]) -> SectionPlanItemDTO:
        section_id = section.get("section_id")
        title = section.get("title")
        execution_order = section.get("execution_order")
        generation_strategy = section.get("generation_strategy") or DEFAULT_GENERATION_STRATEGY

        if not section_id:
            raise ValidationError(
                message="section_id is required in resolved section",
                error_code="SECTION_PLAN_INVALID",
                details={"field": "section_id"},
            )

        if not title:
            raise ValidationError(
                message="title is required in resolved section",
                error_code="SECTION_PLAN_INVALID",
                details={"field": "title", "section_id": section_id},
            )

        if execution_order is None:
            raise ValidationError(
                message="execution_order is required in resolved section",
                error_code="SECTION_PLAN_INVALID",
                details={"field": "execution_order", "section_id": section_id},
            )

        retrieval_profile = (
            section.get("retrieval_profile")
            or self._derive_retrieval_profile(section, generation_strategy)
        )

        dependencies = section.get("dependencies") or []
        if not isinstance(dependencies, list):
            raise ValidationError(
                message="dependencies must be a list",
                error_code="SECTION_PLAN_INVALID",
                details={"field": "dependencies", "section_id": section_id},
            )

        metadata = dict(section)
        metadata.pop("section_id", None)
        metadata.pop("title", None)
        metadata.pop("execution_order", None)
        metadata.pop("generation_strategy", None)
        metadata.pop("retrieval_profile", None)
        metadata.pop("dependencies", None)

        return SectionPlanItemDTO(
            section_id=section_id,
            title=title,
            execution_order=int(execution_order),
            generation_strategy=generation_strategy,
            retrieval_profile=retrieval_profile,
            dependencies=dependencies,
            metadata=metadata,
        )

    def _derive_retrieval_profile(
        self,
        section: dict[str, Any],
        generation_strategy: str,
    ) -> str:
        """
        Derive a retrieval profile from the section metadata and generation strategy.
        """
        title = str(section.get("title", "")).lower()

        if generation_strategy == "generate_table":
            return "table"

        if generation_strategy == "diagram_plantuml":
            return "diagram"

        if "architecture" in title:
            return "architecture"

        if "requirement" in title:
            return "requirements"

        if "api" in title:
            return "api"

        return DEFAULT_RETRIEVAL_PROFILE