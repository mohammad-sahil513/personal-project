"""
File-based repository for document metadata.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.core.config import get_settings
from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.core.logging import get_logger

logger = get_logger(__name__)


class DocumentRepository:
    """
    Repository for document metadata records stored as JSON files.
    """

    def __init__(self, base_path: Path | None = None) -> None:
        settings = get_settings()
        self.base_path = base_path or settings.documents_path
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _file_path(self, document_id: str) -> Path:
        return self.base_path / f"{document_id}.json"

    def create(self, record: dict[str, Any]) -> dict[str, Any]:
        document_id = record.get("document_id")
        if not document_id:
            raise ValidationError(
                message="document_id is required",
                details={"field": "document_id"},
            )

        file_path = self._file_path(document_id)
        if file_path.exists():
            raise ConflictError(
                message=f"Document '{document_id}' already exists",
                error_code="DOCUMENT_ALREADY_EXISTS",
            )

        file_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("Document record created", extra={"document_id": document_id})
        return record

    def get(self, document_id: str) -> dict[str, Any]:
        file_path = self._file_path(document_id)
        if not file_path.exists():
            raise NotFoundError(
                message=f"Document '{document_id}' not found",
                error_code="DOCUMENT_NOT_FOUND",
            )

        return json.loads(file_path.read_text(encoding="utf-8"))

    def list(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []

        for file_path in sorted(self.base_path.glob("*.json")):
            items.append(json.loads(file_path.read_text(encoding="utf-8")))

        return items

    def update(self, document_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        current = self.get(document_id)
        current.update(updates)

        file_path = self._file_path(document_id)
        file_path.write_text(json.dumps(current, indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info("Document record updated", extra={"document_id": document_id})
        return current

    def delete(self, document_id: str) -> bool:
        file_path = self._file_path(document_id)
        if not file_path.exists():
            raise NotFoundError(
                message=f"Document '{document_id}' not found",
                error_code="DOCUMENT_NOT_FOUND",
            )

        file_path.unlink()
        logger.info("Document record deleted", extra={"document_id": document_id})

        bin_path = self._bin_path(document_id)
        if bin_path.exists():
            bin_path.unlink()

        return True

    def _bin_path(self, document_id: str) -> Path:
        return self.base_path / f"{document_id}.bin"

    def save_binary(self, document_id: str, data: bytes) -> None:
        bin_path = self._bin_path(document_id)
        bin_path.write_bytes(data)
        logger.info("Document binary saved", extra={"document_id": document_id, "size": len(data)})

    def get_binary(self, document_id: str) -> bytes:
        bin_path = self._bin_path(document_id)
        if not bin_path.exists():
            raise NotFoundError(
                message=f"Document binary '{document_id}' not found",
                error_code="DOCUMENT_BINARY_NOT_FOUND",
            )
        return bin_path.read_bytes()