"""
Application service for document metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.application.dto.document_dto import DocumentDTO
from backend.core.ids import generate_document_id
from backend.repositories.document_repository import DocumentRepository


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DocumentService:
    """
    Backend use-case service for document metadata handling.
    """

    def __init__(self, repository: DocumentRepository | None = None) -> None:
        self.repository = repository or DocumentRepository()

    def create_document(
        self,
        *,
        filename: str,
        content_type: str,
        size: int,
        file_bytes: bytes | None = None,
        status: str = "AVAILABLE",
    ) -> DocumentDTO:
        record = {
            "document_id": generate_document_id(),
            "filename": filename,
            "content_type": content_type,
            "size": size,
            "uploaded_at": _utc_now_iso(),
            "status": status,
        }

        created = self.repository.create(record)
        if file_bytes is not None:
            self.repository.save_binary(created["document_id"], file_bytes)
            
        return DocumentDTO(**created)

    def get_document(self, document_id: str) -> DocumentDTO:
        record = self.repository.get(document_id)
        return DocumentDTO(**record)

    def get_document_bytes(self, document_id: str) -> bytes:
        return self.repository.get_binary(document_id)

    def list_documents(self) -> list[DocumentDTO]:
        records = self.repository.list()
        return [DocumentDTO(**record) for record in records]


    def update_document(self, document_id: str, updates: dict[str, Any]) -> DocumentDTO:
        updated = self.repository.update(document_id, updates)
        return DocumentDTO(**updated)

    def delete_document(self, document_id: str) -> bool:
        return self.repository.delete(document_id)