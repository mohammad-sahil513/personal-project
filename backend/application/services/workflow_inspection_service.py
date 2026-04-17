"""
Application service for workflow inspection (errors, artifacts, diagnostics).
"""

from __future__ import annotations

from backend.application.services.workflow_event_service import get_workflow_event_service
from backend.application.services.workflow_service import WorkflowService
from backend.core.exceptions import NotFoundError


class WorkflowInspectionService:
    """
    Read-only inspection helpers for workflows.
    """

    def __init__(self, workflow_service: WorkflowService | None = None) -> None:
        self.workflow_service = workflow_service or WorkflowService()
        self.event_service = get_workflow_event_service()

    def get_errors(self, workflow_run_id: str) -> dict:
        workflow = self.workflow_service.get_workflow(workflow_run_id)
        return {
            "workflow_run_id": workflow_run_id,
            "status": workflow.status,
            "errors": workflow.errors or [],
        }

    def get_artifacts(self, workflow_run_id: str) -> dict:
        workflow = self.workflow_service.get_workflow(workflow_run_id)

        artifacts = []

        if workflow.assembled_document:
            artifacts.append(
                {
                    "type": "ASSEMBLED_PREVIEW",
                    "format": "JSON",
                    "description": "Assembled document preview",
                }
            )

        if workflow.output_id:
            artifacts.append(
                {
                    "type": "OUTPUT",
                    "format": "DOCX",
                    "output_id": workflow.output_id,
                }
            )

        return {
            "workflow_run_id": workflow_run_id,
            "artifacts": artifacts,
        }

    def get_recent_events(self, workflow_run_id: str, limit: int = 20) -> dict:
        events = self.event_service.get_recent_events(workflow_run_id, limit=limit)
        return {
            "workflow_run_id": workflow_run_id,
            "events": [e.to_dict() for e in events],
        }

    def get_diagnostics(self, workflow_run_id: str) -> dict:
        workflow = self.workflow_service.get_workflow(workflow_run_id)

        return {
            "workflow_run_id": workflow_run_id,
            "status": workflow.status,
            "current_phase": workflow.current_phase,
            "overall_progress_percent": workflow.overall_progress_percent,
            "has_errors": bool(workflow.errors),
            "has_output": bool(workflow.output_id),
            "sections": {
                "planned": workflow.section_plan.get("total_sections")
                if workflow.section_plan
                else 0,
                "completed": workflow.section_progress.get("completed_sections")
                if workflow.section_progress
                else 0,
                "failed": workflow.section_progress.get("failed_sections")
                if workflow.section_progress
                else 0,
            },
        }