"""
File-based repository for workflow run metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.core.config import get_settings
from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger

logger = get_logger(__name__)


class WorkflowRepository:
    """
    Repository for workflow run metadata records stored as JSON files.
    """

    def __init__(self, base_path: Path | None = None) -> None:
        settings = get_settings()
        self.base_path = base_path or settings.workflow_runs_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _file_path(self, workflow_run_id: str) -> Path:
        return self.base_path / f"{workflow_run_id}.json"

    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        workflow_run_id = record.get("workflow_run_id")
        if not workflow_run_id:
            raise ValidationError(
                message="workflow_run_id is required",
                details={"field": "workflow_run_id"},
            )

        file_path = self._file_path(workflow_run_id)
        if file_path.exists():
            raise ConflictError(
                message=f"Workflow '{workflow_run_id}' already exists",
                error_code="WORKFLOW_ALREADY_EXISTS",
            )

        file_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Workflow record created", extra={"workflow_run_id": workflow_run_id})
        return record

    def get(self, workflow_run_id: str) -> dict[str, Any]:
        file_path = self._file_path(workflow_run_id)
        if not file_path.exists():
            raise NotFoundError(
                message=f"Workflow '{workflow_run_id}' not found",
                error_code="WORKFLOW_NOT_FOUND",
            )

        return json.loads(file_path.read_text(encoding="utf-8"))

    def list(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []

        for file_path in sorted(self.base_path.glob("*.json")):
            items.append(json.loads(file_path.read_text(encoding="utf-8")))

        return items

    def update(self, workflow_run_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get(workflow_run_id)
        current.update(updates)

        file_path = self._file_path(workflow_run_id)
        file_path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info("Workflow record updated", extra={"workflow_run_id": workflow_run_id})
        return current

    def delete(self, workflow_run_id: str) -> bool:
        file_path = self._file_path(workflow_run_id)
        if not file_path.exists():
            raise NotFoundError(
                message=f"Workflow '{workflow_run_id}' not found",
                error_code="WORKFLOW_NOT_FOUND",
            )

        file_path.unlink()
        logger.info("Workflow record deleted", extra={"workflow_run_id": workflow_run_id})
        return True