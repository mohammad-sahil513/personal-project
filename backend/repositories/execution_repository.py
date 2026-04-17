"""
File-based repository for execution metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.core.config import get_settings
from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger

logger = get_logger(__name__)


class ExecutionRepository:
    """
    Repository for execution metadata records stored as JSON files.
    """

    def __init__(self, base_path: Path | None = None) -> None:
        settings = get_settings()
        self.base_path = base_path or settings.executions_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _file_path(self, execution_id: str) -> Path:
        return self.base_path / f"{execution_id}.json"

    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        execution_id = record.get("execution_id")
        if not execution_id:
            raise ValidationError(
                message="execution_id is required",
                details={"field": "execution_id"},
            )

        file_path = self._file_path(execution_id)
        if file_path.exists():
            raise ConflictError(
                message=f"Execution '{execution_id}' already exists",
                error_code="EXECUTION_ALREADY_EXISTS",
            )

        file_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Execution record created", extra={"execution_id": execution_id})
        return record

    def get(self, execution_id: str) -> dict[str, Any]:
        file_path = self._file_path(execution_id)
        if not file_path.exists():
            raise NotFoundError(
                message=f"Execution '{execution_id}' not found",
                error_code="EXECUTION_NOT_FOUND",
            )

        return json.loads(file_path.read_text(encoding="utf-8"))

    def list(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []

        for file_path in sorted(self.base_path.glob("*.json")):
            items.append(json.loads(file_path.read_text(encoding="utf-8")))

        return items

    def update(self, execution_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get(execution_id)
        current.update(updates)

        file_path = self._file_path(execution_id)
        file_path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info("Execution record updated", extra={"execution_id": execution_id})
        return current

    def delete(self, execution_id: str) -> bool:
        file_path = self._file_path(execution_id)
        if not file_path.exists():
            raise NotFoundError(
                message=f"Execution '{execution_id}' not found",
                error_code="EXECUTION_NOT_FOUND",
            )

        file_path.unlink()
        logger.info("Execution record deleted", extra={"execution_id": execution_id})
        return True