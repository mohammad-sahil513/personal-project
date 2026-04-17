"""
Application service for workflow-level section generation execution.
"""

from __future__ import annotations

from backend.application.services.section_generation_service import SectionGenerationService
from backend.core.exceptions import ValidationError


class WorkflowSectionGenerationService:
    """
    Execute generation for all sections in a workflow.
    """

    def __init__(
        self,
        section_generation_service: SectionGenerationService | None = None,
    ) -> None:
        self.section_generation_service = (
            section_generation_service or SectionGenerationService()
        )

    async def run_generation_for_workflow(
        self,
        *,
        section_plan: dict,
        section_retrieval_results: dict,
        workflow_run_id: str | None = None,
        document_id: str | None = None,
        template_id: str | None = None,
        template_version: str | None = None,
    ) -> dict[str, dict]:
        if not section_plan:
            raise ValidationError(
                message="section_plan is required for workflow generation",
                error_code="WORKFLOW_GENERATION_INVALID",
                details={"field": "section_plan"},
            )

        if not section_retrieval_results:
            raise ValidationError(
                message="section_retrieval_results is required for workflow generation",
                error_code="WORKFLOW_GENERATION_INVALID",
                details={"field": "section_retrieval_results"},
            )

        sections = section_plan.get("sections")
        if not sections:
            raise ValidationError(
                message="section_plan.sections is required",
                error_code="WORKFLOW_GENERATION_INVALID",
                details={"field": "sections"},
            )

        results: dict[str, dict] = {}

        for section in sections:
            section_id = section.get("section_id")
            retrieval_result = section_retrieval_results.get(section_id)

            if retrieval_result is None:
                raise ValidationError(
                    message="Missing retrieval result for section",
                    error_code="WORKFLOW_GENERATION_INVALID",
                    details={"section_id": section_id},
                )

            generation_result = await self.section_generation_service.generate_for_section(
                section_plan_item=section,
                retrieval_result=retrieval_result,
                workflow_run_id=workflow_run_id,
                document_id=document_id,
                template_id=template_id,
                template_version=template_version,
            )

            results[section_id] = generation_result.to_dict()

        return results