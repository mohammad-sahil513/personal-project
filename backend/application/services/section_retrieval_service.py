"""
Application service for section-level retrieval execution.
"""

from __future__ import annotations

from backend.application.dto.retrieval_dto import RetrievalResultDTO
from backend.application.services.retrieval_runtime_bridge import RetrievalRuntimeBridge
from backend.core.exceptions import ValidationError


class SectionRetrievalService:
    """
    Backend use-case service for retrieving evidence for a single section plan item.
    """

    def __init__(
        self,
        retrieval_runtime_bridge: RetrievalRuntimeBridge | None = None,
    ) -> None:
        self.retrieval_runtime_bridge = retrieval_runtime_bridge or RetrievalRuntimeBridge()

    async def retrieve_for_section(
        self,
        section_plan_item: dict,
        *,
        workflow_run_id: str | None = None,
        document_id: str | None = None,
        template_id: str | None = None,
    ) -> RetrievalResultDTO:
        """
        Execute retrieval for a single normalized section-plan item dict.
        """
        if not section_plan_item:
            raise ValidationError(
                message="section_plan_item is required",
                error_code="SECTION_RETRIEVAL_INVALID",
                details={"field": "section_plan_item"},
            )

        section_id = section_plan_item.get("section_id")
        title = section_plan_item.get("title")
        retrieval_profile = section_plan_item.get("retrieval_profile")
        generation_strategy = section_plan_item.get("generation_strategy")

        if not section_id:
            raise ValidationError(
                message="section_id is required in section plan item",
                error_code="SECTION_RETRIEVAL_INVALID",
                details={"field": "section_id"},
            )

        if not title:
            raise ValidationError(
                message="title is required in section plan item",
                error_code="SECTION_RETRIEVAL_INVALID",
                details={"field": "title", "section_id": section_id},
            )

        if not retrieval_profile:
            raise ValidationError(
                message="retrieval_profile is required in section plan item",
                error_code="SECTION_RETRIEVAL_INVALID",
                details={"field": "retrieval_profile", "section_id": section_id},
            )

        if not generation_strategy:
            raise ValidationError(
                message="generation_strategy is required in section plan item",
                error_code="SECTION_RETRIEVAL_INVALID",
                details={"field": "generation_strategy", "section_id": section_id},
            )

        result = await self.retrieval_runtime_bridge.run_retrieval(
            section_id=section_id,
            title=title,
            retrieval_profile=retrieval_profile,
            generation_strategy=generation_strategy,
            workflow_run_id=workflow_run_id,
            document_id=document_id,
            template_id=template_id,
            dependencies=section_plan_item.get("dependencies", []),
            metadata=section_plan_item.get("metadata", {}),
        )

        return RetrievalResultDTO(**result)