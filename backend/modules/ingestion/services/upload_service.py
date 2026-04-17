"""
Upload service for Stage 1 ingestion.

Responsibilities:
- validate supported file types (.pdf / .docx)
- compute deterministic SHA256 hashes
- upload the source document to the shared Azure Blob container
- check for duplicate content in the ingestion repository
- create a persisted ingestion job record
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Protocol
from uuid import uuid4

from backend.modules.ingestion.contracts.stage_1_contracts import (
    BlobArtifactReference,
    IngestionJobRecord,
    IngestionJobStatus,
    IngestionStageName,
    Stage1Input,
    Stage1Metrics,
    Stage1Output,
    StageExecutionStatus,
    StageStatusRecord,
    StageWarning,
    SupportedDocumentExtension,
)
from backend.modules.ingestion.exceptions import BlobStorageError, UnsupportedDocumentTypeError
from backend.modules.ingestion.repositories.ingestion_repository import IngestionRepository


class BlobStorageClientProtocol(Protocol):
    """
    Minimal upload contract expected from the storage client.

    The real infrastructure blob client can implement this same method signature.
    """

    async def upload_bytes(
        self,
        *,
        container_name: str,
        blob_path: str,
        data: bytes,
        content_type: str,
        overwrite: bool = True,
    ) -> BlobArtifactReference:
        """
        Upload bytes and return a blob artifact reference.

        Returning a `BlobArtifactReference` keeps the service fully typed and avoids
        leaking Azure SDK response objects into the domain layer.
        """
        ...


class UploadService:
    """Service class for Stage 1 document upload and deduplication."""

    _SUPPORTED_CONTENT_TYPES: dict[str, str] = {
        SupportedDocumentExtension.PDF.value: "application/pdf",
        SupportedDocumentExtension.DOCX.value: (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
    }

    def __init__(
        self,
        *,
        blob_client: BlobStorageClientProtocol,
        repository: IngestionRepository,
        blob_container_name: str,
        blob_root_prefix: str = "sahil_storage/",
    ) -> None:
        self._blob_client = blob_client
        self._repository = repository
        self._blob_container_name = blob_container_name
        self._blob_root_prefix = blob_root_prefix.rstrip("/") + "/"

    async def upload_and_deduplicate(self, request: Stage1Input) -> Stage1Output:
        """
        Upload the source document, check for duplicate content, and persist a job record.

        Notes:
        - The blob path is deterministic from the SHA256 hash so repeated uploads of the
          same file content remain idempotent at the storage level.
        - Deduplication is based on the canonical hash registry held by the ingestion
          repository.
        """
        total_start = perf_counter()
        process_id = uuid4().hex
        document_id = uuid4().hex

        self._validate_supported_document(request)

        sha256_hash = self.compute_sha256(request.file_bytes)
        blob_path = self.build_source_blob_path(
            sha256_hash=sha256_hash,
            original_file_name=request.file_name,
        )

        upload_start = perf_counter()
        try:
            original_file_artifact = await self._blob_client.upload_bytes(
                container_name=self._blob_container_name,
                blob_path=blob_path,
                data=request.file_bytes,
                content_type=request.content_type,
                overwrite=True,
            )
        except Exception as exc:  # pragma: no cover - infrastructure wrapper
            raise BlobStorageError(
                "Failed to upload source document to Azure Blob Storage.",
                context={"file_name": request.file_name, "blob_path": blob_path},
            ) from exc
        upload_duration_ms = (perf_counter() - upload_start) * 1000

        duplicate_lookup_start = perf_counter()
        existing_job = await self._repository.get_job_by_sha256_hash(sha256_hash)
        duplicate_lookup_duration_ms = (perf_counter() - duplicate_lookup_start) * 1000

        is_duplicate = existing_job is not None
        duplicate_of_document_id = existing_job.document_id if existing_job else None

        warnings: list[StageWarning] = []
        if is_duplicate:
            warnings.append(
                StageWarning(
                    code="DUPLICATE_DOCUMENT_DETECTED",
                    message="A document with the same SHA256 hash already exists.",
                    details={
                        "sha256_hash": sha256_hash,
                        "duplicate_of_document_id": duplicate_of_document_id,
                    },
                )
            )

        stage_status_record = StageStatusRecord(
            stage_name=IngestionStageName.UPLOAD_AND_DEDUP,
            status=StageExecutionStatus.COMPLETED,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            warnings=warnings,
            details={
                "file_name": request.file_name,
                "content_type": request.content_type,
            },
        )

        job_record = IngestionJobRecord(
            process_id=process_id,
            document_id=document_id,
            file_name=request.file_name,
            content_type=request.content_type,
            sha256_hash=sha256_hash,
            source_blob=original_file_artifact,
            status=IngestionJobStatus.DUPLICATE if is_duplicate else IngestionJobStatus.IN_PROGRESS,
            current_stage=IngestionStageName.UPLOAD_AND_DEDUP,
            is_duplicate=is_duplicate,
            duplicate_of_document_id=duplicate_of_document_id,
            initiated_by=request.initiated_by,
            correlation_id=request.correlation_id,
            source_metadata=request.source_metadata,
            stage_statuses={IngestionStageName.UPLOAD_AND_DEDUP.value: stage_status_record},
        )

        await self._repository.create_or_replace_job(job_record)

        total_duration_ms = (perf_counter() - total_start) * 1000
        metrics = Stage1Metrics(
            file_size_bytes=len(request.file_bytes),
            upload_duration_ms=round(upload_duration_ms, 3),
            duplicate_lookup_duration_ms=round(duplicate_lookup_duration_ms, 3),
            total_duration_ms=round(total_duration_ms, 3),
        )

        return Stage1Output(
            process_id=process_id,
            document_id=document_id,
            sha256_hash=sha256_hash,
            original_file=original_file_artifact,
            is_duplicate=is_duplicate,
            duplicate_of_document_id=duplicate_of_document_id,
            job_record=job_record,
            warnings=warnings,
            metrics=metrics,
        )

    def compute_sha256(self, file_bytes: bytes) -> str:
        """Return the lowercase SHA256 hex digest for the uploaded content."""
        return hashlib.sha256(file_bytes).hexdigest()

    def build_source_blob_path(self, *, sha256_hash: str, original_file_name: str) -> str:
        """
        Build a deterministic blob path under the required shared root prefix.

        Path example:
        sahil_storage/ingestion/source_documents/{sha256_hash}/original_filename.pdf
        """
        safe_file_name = self._sanitize_file_name(original_file_name)
        return (
            f"{self._blob_root_prefix}"
            f"ingestion/source_documents/{sha256_hash}/{safe_file_name}"
        )

    def _validate_supported_document(self, request: Stage1Input) -> None:
        """Validate the file extension and expected MIME type for Stage 1 input."""
        extension = Path(request.file_name).suffix.lower()

        if extension not in self._SUPPORTED_CONTENT_TYPES:
            raise UnsupportedDocumentTypeError(
                "Only structured PDF and DOCX documents are supported.",
                context={
                    "file_name": request.file_name,
                    "file_extension": extension,
                },
            )

        expected_content_type = self._SUPPORTED_CONTENT_TYPES[extension]
        if request.content_type != expected_content_type:
            raise UnsupportedDocumentTypeError(
                "The content type does not match the file extension.",
                context={
                    "file_name": request.file_name,
                    "file_extension": extension,
                    "content_type": request.content_type,
                    "expected_content_type": expected_content_type,
                },
            )

    @staticmethod
    def _sanitize_file_name(file_name: str) -> str:
        """
        Sanitize a file name for storage safety.

        We intentionally keep the original extension because later stages may
        need to inspect the source artifact type.
        """
        sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name.strip())
        return sanitized or "uploaded_document"