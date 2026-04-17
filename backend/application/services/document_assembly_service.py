"""
Application service for assembling section generation results into a preview document.
"""

from __future__ import annotations

from backend.application.dto.assembled_document_dto import (
    AssembledDocumentDTO,
    AssembledSectionDTO,
)
from backend.core.exceptions import ValidationError


class DocumentAssemblyService:
    """
    Backend use-case service for assembling ordered generated sections into a
    single document preview structure.
    """

    def build_assembled_document(
        self,
        *,
        workflow_run_id: str,
        template_id: str | None,
        section_plan: dict,
        section_generation_results: dict,
        title: str | None = None,
    ) -> AssembledDocumentDTO:
        if not section_plan:
            raise ValidationError(
                message="section_plan is required for document assembly",
                error_code="ASSEMBLY_INVALID",
                details={"field": "section_plan"},
            )

        if not section_generation_results:
            raise ValidationError(
                message="section_generation_results is required for document assembly",
                error_code="ASSEMBLY_INVALID",
                details={"field": "section_generation_results"},
            )

        sections = section_plan.get("sections")
        if not sections:
            raise ValidationError(
                message="section_plan.sections is required",
                error_code="ASSEMBLY_INVALID",
                details={"field": "sections"},
            )

        assembled_sections: list[AssembledSectionDTO] = []

        sorted_sections = sorted(
            sections,
            key=lambda item: item["execution_order"],
        )

        for section in sorted_sections:
            section_id = section["section_id"]
            generation_result = section_generation_results.get(section_id)

            if generation_result is None:
                raise ValidationError(
                    message="Missing generation result for section during assembly",
                    error_code="ASSEMBLY_INVALID",
                    details={"section_id": section_id},
                )

            assembled_sections.append(
                AssembledSectionDTO(
                    section_id=section_id,
                    title=section["title"],
                    execution_order=section["execution_order"],
                    output_type=generation_result["output_type"],
                    content=generation_result.get("content"),
                    artifacts=generation_result.get("artifacts", []),
                    metadata={
                        "generation_strategy": section.get("generation_strategy"),
                        "retrieval_profile": section.get("retrieval_profile"),
                        "dependencies": section.get("dependencies", []),
                    },
                )
            )

        document_title = title or f"Assembled Document ({workflow_run_id})"

        return AssembledDocumentDTO(
            workflow_run_id=workflow_run_id,
            template_id=template_id,
            total_sections=len(assembled_sections),
            title=document_title,
            sections=assembled_sections,
        )