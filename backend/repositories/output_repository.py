"""
File-based repository for workflow outputs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.core.config import get_settings
from backend.core.exceptions import ConflictError, NotFoundError
from backend.core.logging import get_logger

logger = get_logger(__name__)


class OutputRepository:
    """
    Repository for workflow output metadata stored as JSON files.
    """

    def __init__(self, base_path: Path | None = None) -> None:
        settings = get_settings()
        self.base_path = base_path or settings.outputs_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _file_path(self, output_id: str) -> Path:
        return self.base_path / f"{output_id}.json"

    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        file_path = self._file_path(record["output_id"])
        if file_path.exists():
            raise ConflictError(
                message="Output already exists",
                error_code="OUTPUT_ALREADY_EXISTS",
            )

        file_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        logger.info("Output record created", extra={"output_id": record["output_id"]})
        return record

    def get(self, output_id: str) -> dict[str, Any]:
        file_path = self._file_path(output_id)
        if not file_path.exists():
            raise NotFoundError(
                message="Output not found",
                error_code="OUTPUT_NOT_FOUND",
            )

        return json.loads(file_path.read_text(encoding="utf-8"))

    def update(self, output_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get(output_id)
        current.update(updates)

        self._file_path(output_id).write_text(
            json.dumps(current, indent=2),
            encoding="utf-8",
        )
        logger.info("Output record updated", extra={"output_id": output_id})
        return current