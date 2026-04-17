"""
Application service for workflow metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.application.dto.workflow_dto import WorkflowDTO
from backend.core.ids import generate_execution_id, generate_workflow_run_id
from backend.repositories.execution_repository import ExecutionRepository
from backend.repositories.workflow_repository import WorkflowRepository


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WorkflowService:
    """
    Backend use-case service for workflow lifecycle metadata.
    """

    def __init__(
        self,
        workflow_repository: WorkflowRepository | None = None,
        execution_repository: ExecutionRepository | None = None,
    ) -> None:
        self.workflow_repository = workflow_repository or WorkflowRepository()
        self.execution_repository = execution_repository or ExecutionRepository()

    def create_workflow(
        self,
        *,
        document_id: str,
        template_id: str | None = None,
        initial_status: str = "PENDING",
        current_phase: str = "INPUT_PREPARATION",
    ) -> WorkflowDTO:
        now = _utc_now_iso()

        workflow_record = {
            "workflow_run_id": generate_workflow_run_id(),
            "status": initial_status,
            "current_phase": current_phase,
            "overall_progress_percent": 0,
            "document_id": document_id,
            "template_id": template_id,
            "output_id": None,
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "completed_at": None,
            "phases": [],
            "execution_refs": {},
            "section_plan": None,
            "section_progress": None,
            "section_retrieval_results": None,
            "section_generation_results": None,
            "assembled_document": None,
            "observability_summary": None,
            "warnings": [],
            "errors": [],
        }

        created_workflow = self.workflow_repository.create(workflow_record)

        execution_record = {
            "execution_id": generate_execution_id(),
            "workflow_run_id": created_workflow["workflow_run_id"],
            "type": "WORKFLOW",
            "status": initial_status,
            "created_at": now,
            "updated_at": now,
        }
        self.execution_repository.create(execution_record)

        return WorkflowDTO(**created_workflow)

    def get_workflow(self, workflow_run_id: str) -> WorkflowDTO:
        record = self.workflow_repository.get(workflow_run_id)
        return WorkflowDTO(**record)

    def list_workflows(self) -> list:
        records = self.workflow_repository.list()
        return [WorkflowDTO(**record) for record in records]

    def update_workflow(self, workflow_run_id: str, updates: dict[str, Any]) -> WorkflowDTO:
        updates["updated_at"] = _utc_now_iso()
        updated = self.workflow_repository.update(workflow_run_id, updates)
        return WorkflowDTO(**updated)

    def attach_execution_ref(
        self,
        workflow_run_id: str,
        *,
        execution_type: str,
        execution_id: str,
    ) -> WorkflowDTO:
        current = self.get_workflow(workflow_run_id)
        refs = dict(current.execution_refs or {})
        refs[execution_type] = execution_id

        return self.update_workflow(
            workflow_run_id,
            {
                "execution_refs": refs,
            },
        )

    def attach_section_plan(
        self,
        workflow_run_id: str,
        *,
        section_plan: dict[str, Any],
    ) -> WorkflowDTO:
        return self.update_workflow(
            workflow_run_id,
            {
                "section_plan": section_plan,
            },
        )

    def attach_section_progress(
        self,
        workflow_run_id: str,
        *,
        section_progress: dict[str, Any],
    ) -> WorkflowDTO:
        return self.update_workflow(
            workflow_run_id,
            {
                "section_progress": section_progress,
            },
        )

    def attach_section_retrieval_results(
        self,
        workflow_run_id: str,
        *,
        section_retrieval_results: dict[str, Any],
    ) -> WorkflowDTO:
        return self.update_workflow(
            workflow_run_id,
            {
                "section_retrieval_results": section_retrieval_results,
            },
        )

    def attach_section_generation_results(
        self,
        workflow_run_id: str,
        *,
        section_generation_results: dict[str, Any],
    ) -> WorkflowDTO:
        return self.update_workflow(
            workflow_run_id,
            {
                "section_generation_results": section_generation_results,
            },
        )

    def attach_assembled_document(
        self,
        workflow_run_id: str,
        *,
        assembled_document: dict[str, Any],
    ) -> WorkflowDTO:
        return self.update_workflow(
            workflow_run_id,
            {
                "assembled_document": assembled_document,
            },
        )

    def update_progress_from_sections(
        self,
        workflow_run_id: str,
        *,
        overall_progress_percent: int,
    ) -> WorkflowDTO:
        return self.update_workflow(
            workflow_run_id,
            {
                "overall_progress_percent": overall_progress_percent,
            },
        )

    def mark_workflow_started(self, workflow_run_id: str) -> WorkflowDTO:
        now = _utc_now_iso()
        return self.update_workflow(
            workflow_run_id,
            {
                "status": "RUNNING",
                "started_at": now,
            },
        )

    def mark_workflow_completed(self, workflow_run_id: str, output_id: str | None = None) -> WorkflowDTO:
        now = _utc_now_iso()
        return self.update_workflow(
            workflow_run_id,
            {
                "status": "COMPLETED",
                "completed_at": now,
                "overall_progress_percent": 100,
                "output_id": output_id,
            },
        )

    def mark_workflow_failed(
        self,
        workflow_run_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> WorkflowDTO:
        current = self.get_workflow(workflow_run_id)
        errors = list(current.errors or [])
        errors.append(
            {
                "code": error_code,
                "message": error_message,
            }
        )

        return self.update_workflow(
            workflow_run_id,
            {
                "status": "FAILED",
                "errors": errors,
            },
        )
    def attach_output(
        self,
        workflow_run_id: str,
        *,
        output_id: str,
    ) -> WorkflowDTO:
        return self.update_workflow(
            workflow_run_id,
            {
                "output_id": output_id,
            },
        )