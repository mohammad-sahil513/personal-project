"""
Backend integration service for ingestion execution metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.application.dto.ingestion_dto import IngestionExecutionDTO
from backend.core.ids import generate_execution_id
from backend.repositories.execution_repository import ExecutionRepository

INGESTION_STAGE_ORDER: list[str] = [
    "01_UPLOAD_AND_DEDUP",
    "02_PARSE_DOCUMENT",
    "03_MASK_PII",
    "04_CLASSIFY_IMAGES",
    "05_VISION_EXTRACTION",
    "06_SEGMENT_SECTIONS",
    "07_VALIDATE_OUTPUTS",
    "08_SEMANTIC_CHUNKING",
    "09_VECTOR_INDEXING",
]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class IngestionIntegrationService:
    """
    Backend-facing service for managing ingestion child-execution metadata.
    """

    def __init__(self, execution_repository: ExecutionRepository | None = None) -> None:
        self.execution_repository = execution_repository or ExecutionRepository()

    def create_ingestion_execution(
        self,
        *,
        workflow_run_id: str,
        document_id: str,
    ) -> IngestionExecutionDTO:
        now = _utc_now_iso()

        record = {
            "execution_id": generate_execution_id(),
            "workflow_run_id": workflow_run_id,
            "document_id": document_id,
            "type": "INGESTION",
            "status": "PENDING",
            "current_stage": INGESTION_STAGE_ORDER[0],
            "completed_stages": 0,
            "total_stages": len(INGESTION_STAGE_ORDER),
            "created_at": now,
            "updated_at": now,
            "warnings": [],
            "errors": [],
            "artifacts": [],
        }

        created = self.execution_repository.create(record)
        return IngestionExecutionDTO(**created)

    def get_ingestion_execution(self, execution_id: str) -> IngestionExecutionDTO:
        record = self.execution_repository.get(execution_id)
        return IngestionExecutionDTO(**record)

    def find_ingestion_execution_for_workflow(
        self,
        workflow_run_id: str,
    ) -> IngestionExecutionDTO | None:
        records = self.execution_repository.list()

        for record in records:
            if (
                record.get("workflow_run_id") == workflow_run_id
                and record.get("type") == "INGESTION"
            ):
                return IngestionExecutionDTO(**record)

        return None

    def mark_ingestion_running(
        self,
        execution_id: str,
        *,
        current_stage: str | None = None,
    ) -> IngestionExecutionDTO:
        updates = {
            "status": "RUNNING",
            "updated_at": _utc_now_iso(),
        }

        if current_stage is not None:
            updates["current_stage"] = current_stage

        updated = self.execution_repository.update(execution_id, updates)
        return IngestionExecutionDTO(**updated)

    def update_ingestion_stage(
        self,
        execution_id: str,
        *,
        current_stage: str,
        completed_stages: int,
        warnings: list[dict[str, Any]] | None = None,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> IngestionExecutionDTO:
        updates: dict[str, Any] = {
            "status": "RUNNING",
            "current_stage": current_stage,
            "completed_stages": completed_stages,
            "updated_at": _utc_now_iso(),
        }

        if warnings is not None:
            updates["warnings"] = warnings

        if artifacts is not None:
            updates["artifacts"] = artifacts

        updated = self.execution_repository.update(execution_id, updates)
        return IngestionExecutionDTO(**updated)

    def mark_ingestion_completed(
        self,
        execution_id: str,
        *,
        artifacts: list[dict[str, Any]] | None = None,
    ) -> IngestionExecutionDTO:
        updates: dict[str, Any] = {
            "status": "COMPLETED",
            "current_stage": INGESTION_STAGE_ORDER[-1],
            "completed_stages": len(INGESTION_STAGE_ORDER),
            "updated_at": _utc_now_iso(),
        }

        if artifacts is not None:
            updates["artifacts"] = artifacts

        updated = self.execution_repository.update(execution_id, updates)
        return IngestionExecutionDTO(**updated)

    def mark_ingestion_failed(
        self,
        execution_id: str,
        *,
        current_stage: str,
        error_code: str,
        error_message: str,
    ) -> IngestionExecutionDTO:
        current = self.execution_repository.get(execution_id)
        errors = list(current.get("errors", []))
        errors.append(
            {
                "code": error_code,
                "message": error_message,
            }
        )

        updated = self.execution_repository.update(
            execution_id,
            {
                "status": "FAILED",
                "current_stage": current_stage,
                "errors": errors,
                "updated_at": _utc_now_iso(),
            },
        )
        return IngestionExecutionDTO(**updated)
