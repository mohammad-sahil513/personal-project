"""
Application service for workflow-level section retrieval execution.
"""

from __future__ import annotations

from backend.application.services.section_retrieval_service import SectionRetrievalService
from backend.application.services.workflow_event_service import (
    WorkflowEventService,
    get_workflow_event_service,
)
from backend.core.exceptions import ValidationError


class WorkflowSectionRetrievalService:
    """
    Execute retrieval for all sections in a workflow section plan.
    """

    def __init__(
        self,
        section_retrieval_service: SectionRetrievalService | None = None,
        workflow_event_service: WorkflowEventService | None = None,
    ) -> None:
        self.section_retrieval_service = section_retrieval_service or SectionRetrievalService()
        self.workflow_event_service = workflow_event_service or get_workflow_event_service()

    async def run_retrieval_for_workflow(
        self,
        *,
        section_plan: dict,
        workflow_run_id: str | None = None,
        document_id: str | None = None,
        template_id: str | None = None,
    ) -> dict[str, dict]:
        if not section_plan:
            raise ValidationError(
                message="section_plan is required for workflow retrieval",
                error_code="WORKFLOW_RETRIEVAL_INVALID",
                details={"field": "section_plan"},
            )

        sections = section_plan.get("sections")
        if not sections:
            raise ValidationError(
                message="section_plan.sections is required",
                error_code="WORKFLOW_RETRIEVAL_INVALID",
                details={"field": "sections"},
            )

        results: dict[str, dict] = {}

        for section in sections:
            section_id = str(section.get("section_id", ""))
            section_title = str(section.get("title", ""))
            if workflow_run_id:
                await self.workflow_event_service.publish(
                    workflow_run_id=workflow_run_id,
                    event_type="section.retrieval.started",
                    phase="retrieval",
                    payload={
                        "section_id": section_id,
                        "section_title": section_title,
                        "workflow_run_id": workflow_run_id,
                        "document_id": document_id,
                        "template_id": template_id,
                        "stage": "retrieval",
                        "status": "STARTED",
                    },
                )
            try:
                retrieval_result = await self.section_retrieval_service.retrieve_for_section(
                    section,
                    workflow_run_id=workflow_run_id,
                    document_id=document_id,
                    template_id=template_id,
                )
                retrieval_dict = retrieval_result.to_dict()
                diagnostics = retrieval_dict.get("diagnostics", {}) if isinstance(retrieval_dict, dict) else {}
                evidence_bundle = retrieval_dict.get("evidence_bundle", {}) if isinstance(retrieval_dict, dict) else {}
                evidence_items = evidence_bundle.get("items", []) if isinstance(evidence_bundle, dict) else []
                warnings = retrieval_dict.get("warnings", []) if isinstance(retrieval_dict, dict) else []
                fallback_used = bool(diagnostics.get("fallback_used", False)) if isinstance(diagnostics, dict) else False
                retrieval_cost_summary = diagnostics.get("cost_summary", {}) if isinstance(diagnostics, dict) else {}

                if workflow_run_id:
                    await self.workflow_event_service.publish(
                        workflow_run_id=workflow_run_id,
                        event_type="section.retrieval.completed",
                        phase="retrieval",
                        payload={
                            "section_id": retrieval_result.section_id,
                            "workflow_run_id": workflow_run_id,
                            "document_id": document_id,
                            "template_id": template_id,
                            "stage": "retrieval",
                            "status": "COMPLETED",
                            "overall_confidence": retrieval_dict.get("overall_confidence"),
                            "evidence_count": len(evidence_items),
                            "warnings": warnings,
                            "warning_count": len(warnings),
                            "fallback_used": fallback_used,
                            "diagnostics": diagnostics,
                            "retrieval_cost_summary": retrieval_cost_summary,
                        },
                    )
                results[retrieval_result.section_id] = retrieval_dict
            except Exception as exc:
                if workflow_run_id:
                    await self.workflow_event_service.publish(
                        workflow_run_id=workflow_run_id,
                        event_type="section.retrieval.failed",
                        phase="retrieval",
                        payload={
                            "section_id": section_id,
                            "section_title": section_title,
                            "workflow_run_id": workflow_run_id,
                            "document_id": document_id,
                            "template_id": template_id,
                            "stage": "retrieval",
                            "status": "FAILED",
                            "error": str(exc),
                        },
                    )
                raise

        return results
