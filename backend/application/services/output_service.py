"""
Application service for workflow output lifecycle.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.application.dto.output_dto import OutputDTO
from backend.core.ids import generate_output_id
from backend.repositories.output_repository import OutputRepository


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OutputService:
    """
    Backend use-case service for workflow outputs.
    """

    def __init__(self, repository: OutputRepository | None = None) -> None:
        self.repository = repository or OutputRepository()

    def create_output(
        self,
        *,
        workflow_run_id: str,
        output_type: str = "DOCUMENT",
        format: str = "DOCX",
    ) -> OutputDTO:
        now = _utc_now_iso()

        record = {
            "output_id": generate_output_id(),
            "workflow_run_id": workflow_run_id,
            "status": "CREATED",
            "output_type": output_type,
            "format": format,
            "artifact_path": None,
            "metadata": {},
            "errors": [],
            "created_at": now,
            "updated_at": now,
        }

        created = self.repository.create(record)
        return OutputDTO(**created)

    def get_output(self, output_id: str) -> OutputDTO:
        record = self.repository.get(output_id)
        return OutputDTO(**record)

    def mark_output_ready(
        self,
        output_id: str,
        *,
        artifact_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> OutputDTO:
        updated = self.repository.update(
            output_id,
            {
                "status": "READY",
                "artifact_path": artifact_path,
                "metadata": metadata or {},
                "updated_at": _utc_now_iso(),
            },
        )
        return OutputDTO(**updated)

    def mark_output_failed(
        self,
        output_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> OutputDTO:
        updated = self.repository.update(
            output_id,
            {
                "status": "FAILED",
                "errors": [
                    {
                        "code": error_code,
                        "message": error_message,
                    }
                ],
                "updated_at": _utc_now_iso(),
            },
        )
        return OutputDTO(**updated)