"""
Application service for template metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.application.dto.template_dto import TemplateDTO
from backend.core.ids import generate_template_id, generate_job_id
from backend.repositories.template_metadata_repository import TemplateMetadataRepository


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class TemplateAppService:
    """
    Backend use-case service for template metadata handling.
    """

    def __init__(self, repository: TemplateMetadataRepository | None = None) -> None:
        self.repository = repository or TemplateMetadataRepository()

    def create_template(
        self,
        *,
        filename: str,
        template_type: str | None = None,
        version: str | None = None,
        file_bytes: bytes | None = None,
        status: str = "UPLOADED",
    ) -> TemplateDTO:
        now = _utc_now_iso()

        record = {
            "template_id": generate_template_id(),
            "filename": filename,
            "template_type": template_type,
            "version": version,
            "status": status,
            "created_at": now,
            "updated_at": now,
            "compile_job_id": None,
            "compiled_artifacts": [],
        }

        created = self.repository.create(record)
        if file_bytes is not None:
            self.repository.save_binary(created["template_id"], file_bytes)

        return TemplateDTO(**created)

    def get_template(self, template_id: str) -> TemplateDTO:
        record = self.repository.get(template_id)
        return TemplateDTO(**record)

    def get_template_bytes(self, template_id: str) -> bytes:
        return self.repository.get_binary(template_id)

    def list_templates(self) -> list[TemplateDTO]:
        records = self.repository.list()
        return [TemplateDTO(**record) for record in records]

    def update_template(self, template_id: str, updates: dict[str, Any]) -> TemplateDTO:
        updates["updated_at"] = _utc_now_iso()
        updated = self.repository.update(template_id, updates)
        return TemplateDTO(**updated)

    def mark_compile_started(self, template_id: str) -> TemplateDTO:
        return self.update_template(
            template_id,
            {
                "status": "COMPILING",
                "compile_job_id": generate_job_id("tpljob"),
            },
        )

    def mark_compile_completed(
        self,
        template_id: str,
        *,
        compiled_artifacts: list[dict[str, Any]] | None = None,
    ) -> TemplateDTO:
        return self.update_template(
            template_id,
            {
                "status": "COMPILED",
                "compiled_artifacts": compiled_artifacts or [],
            },
        )

    def mark_compile_failed(self, template_id: str) -> TemplateDTO:
        return self.update_template(
            template_id,
            {
                "status": "FAILED",
            },
        )

    def delete_template(self, template_id: str) -> bool:
        return self.repository.delete(template_id)
