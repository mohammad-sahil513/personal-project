"""
Application service for building section execution plans from resolved templates.
"""

from __future__ import annotations

from backend.application.dto.section_plan_dto import SectionPlanDTO
from backend.application.services.template_introspection_service import (
    TemplateIntrospectionService,
)
from backend.pipeline.planners.section_execution_planner import SectionExecutionPlanner


class SectionPlanningService:
    """
    Backend use-case service for producing section execution plans.
    """

    def __init__(
        self,
        template_introspection_service: TemplateIntrospectionService | None = None,
        section_execution_planner: SectionExecutionPlanner | None = None,
    ) -> None:
        self.template_introspection_service = (
            template_introspection_service or TemplateIntrospectionService()
        )
        self.section_execution_planner = (
            section_execution_planner or SectionExecutionPlanner()
        )

    async def build_plan_from_template(self, template_id: str) -> SectionPlanDTO:
        """
        Resolve a template and convert the resolved sections into a normalized
        section execution plan.
        """
        resolved = await self.template_introspection_service.resolve_template(template_id)

        return self.section_execution_planner.build_plan(
            template_id=template_id,
            resolved_sections=resolved["resolved_sections"],
        )

    async def build_plan_dict(self, template_id: str) -> dict:
        """
        Convenience helper for API/workflow callers that prefer plain dicts.
        """
        plan = await self.build_plan_from_template(template_id)
        return plan.to_dict()