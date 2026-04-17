"""
File-based repository for template metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.core.config import get_settings
from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger

logger = get_logger(__name__)


class TemplateMetadataRepository:
    """
    Repository for template metadata records stored as JSON files.
    """

    def __init__(self, base_path: Path | None = None) -> None:
        settings = get_settings()
        self.base_path = base_path or settings.templates_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _file_path(self, template_id: str) -> Path:
        return self.base_path / f"{template_id}.json"

    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        template_id = record.get("template_id")
        if not template_id:
            raise ValidationError(
                message="template_id is required",
                details={"field": "template_id"},
            )

        file_path = self._file_path(template_id)
        if file_path.exists():
            raise ConflictError(
                message=f"Template '{template_id}' already exists",
                error_code="TEMPLATE_ALREADY_EXISTS",
            )

        file_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Template record created", extra={"template_id": template_id})
        return record

    def get(self, template_id: str) -> dict[str, Any]:
        file_path = self._file_path(template_id)
        if not file_path.exists():
            raise NotFoundError(
                message=f"Template '{template_id}' not found",
                error_code="TEMPLATE_NOT_FOUND",
            )

        return json.loads(file_path.read_text(encoding="utf-8"))

    def list(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []

        for file_path in sorted(self.base_path.glob("*.json")):
            items.append(json.loads(file_path.read_text(encoding="utf-8")))

        return items

    def update(self, template_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get(template_id)
        current.update(updates)

        file_path = self._file_path(template_id)
        file_path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info("Template record updated", extra={"template_id": template_id})
        return current

    def delete(self, template_id: str) -> bool:
        file_path = self._file_path(template_id)
        if not file_path.exists():
            raise NotFoundError(
                message=f"Template '{template_id}' not found",
                error_code="TEMPLATE_NOT_FOUND",
            )

        file_path.unlink()
        logger.info("Template record deleted", extra={"template_id": template_id})

        bin_path = self._bin_path(template_id)
        if bin_path.exists():
            bin_path.unlink()

        return True

    def _bin_path(self, template_id: str) -> Path:
        return self.base_path / f"{template_id}.docx"

    def save_binary(self, template_id: str, data: bytes) -> None:
        bin_path = self._bin_path(template_id)
        bin_path.write_bytes(data)
        logger.info("Template binary saved", extra={"template_id": template_id, "size": len(data)})

    def get_binary(self, template_id: str) -> bytes:
        bin_path = self._bin_path(template_id)
        if not bin_path.exists():
            raise NotFoundError(
                message=f"Template binary '{template_id}' not found",
                error_code="TEMPLATE_BINARY_NOT_FOUND",
            )
        return bin_path.read_bytes()