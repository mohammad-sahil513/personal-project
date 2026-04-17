"""
Application service for section-level generation execution.
"""

from __future__ import annotations

from backend.application.dto.generation_dto import GenerationResultDTO
from backend.application.services.generation_runtime_bridge import GenerationRuntimeBridge
from backend.core.exceptions import ValidationError


class SectionGenerationService:
    """
    Backend use-case service for generating output for a single section plan item.
    """

    def __init__(
        self,
        generation_runtime_bridge: GenerationRuntimeBridge | None = None,
    ) -> None:
        self.generation_runtime_bridge = generation_runtime_bridge or GenerationRuntimeBridge()

    async def generate_for_section(
        self,
        section_plan_item: dict,
        retrieval_result: dict,
        *,
        workflow_run_id: str | None = None,
        document_id: str | None = None,
        template_id: str | None = None,
        template_version: str | None = None,
    ) -> GenerationResultDTO:
        """
        Execute generation for a single normalized section-plan item dict and
        a corresponding normalized retrieval result dict.
        """
        if not section_plan_item:
            raise ValidationError(
                message="section_plan_item is required",
                error_code="SECTION_GENERATION_INVALID",
                details={"field": "section_plan_item"},
            )

        if not retrieval_result:
            raise ValidationError(
                message="retrieval_result is required",
                error_code="SECTION_GENERATION_INVALID",
                details={"field": "retrieval_result"},
            )

        section_id = section_plan_item.get("section_id")
        title = section_plan_item.get("title")
        generation_strategy = section_plan_item.get("generation_strategy")

        if not section_id:
            raise ValidationError(
                message="section_id is required in section plan item",
                error_code="SECTION_GENERATION_INVALID",
                details={"field": "section_id"},
            )

        if not title:
            raise ValidationError(
                message="title is required in section plan item",
                error_code="SECTION_GENERATION_INVALID",
                details={"field": "title", "section_id": section_id},
            )

        if not generation_strategy:
            raise ValidationError(
                message="generation_strategy is required in section plan item",
                error_code="SECTION_GENERATION_INVALID",
                details={"field": "generation_strategy", "section_id": section_id},
            )

        result = await self.generation_runtime_bridge.run_generation(
            section_id=section_id,
            title=title,
            generation_strategy=generation_strategy,
            retrieval_result=retrieval_result,
            workflow_run_id=workflow_run_id,
            document_id=document_id,
            template_id=template_id,
            template_version=template_version,
            dependencies=section_plan_item.get("dependencies", []),
            metadata=section_plan_item.get("metadata", {}),
        )

        return GenerationResultDTO(**result)