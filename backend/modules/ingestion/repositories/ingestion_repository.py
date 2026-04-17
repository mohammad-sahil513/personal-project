"""
File-backed ingestion repository.

The project intentionally avoids a database in the initial implementation.
This repository persists ingestion job metadata to local JSON files and keeps
a lightweight hash registry for deduplication lookups.

This repository can later be swapped behind the same abstraction if the system
moves to a database-backed metadata store.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import orjson

from backend.modules.ingestion.contracts.stage_1_contracts import (
    IngestionJobRecord,
    IngestionJobStatus,
    IngestionStageName,
    StageExecutionStatus,
    StageStatusRecord,
    StageWarning,
)
from backend.modules.ingestion.exceptions import RepositoryError


class IngestionRepository:
    """
    File-based repository for ingestion metadata.

    Storage layout:
    - {base_dir}/jobs/{document_id}.json
    - {base_dir}/hash_registry.json

    The hash registry maps SHA256 digests to the canonical (original) document_id.
    """

    def __init__(self, base_dir: str | Path) -> None:
        self._base_dir = Path(base_dir)
        self._jobs_dir = self._base_dir / "jobs"
        self._hash_registry_path = self._base_dir / "hash_registry.json"

    async def initialize(self) -> None:
        """Create required repository directories and files if they do not exist."""
        await asyncio.to_thread(self._initialize_sync)

    async def get_job_by_document_id(self, document_id: str) -> IngestionJobRecord | None:
        """Return the persisted job record for a document ID, if it exists."""
        try:
            return await asyncio.to_thread(self._get_job_by_document_id_sync, document_id)
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise RepositoryError(
                "Failed to fetch ingestion job by document ID.",
                context={"document_id": document_id},
            ) from exc

    async def get_job_by_sha256_hash(self, sha256_hash: str) -> IngestionJobRecord | None:
        """Return the canonical job record for a content hash, if it exists."""
        try:
            return await asyncio.to_thread(self._get_job_by_sha256_hash_sync, sha256_hash)
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise RepositoryError(
                "Failed to fetch ingestion job by SHA256 hash.",
                context={"sha256_hash": sha256_hash},
            ) from exc

    async def create_or_replace_job(self, job_record: IngestionJobRecord) -> None:
        """
        Persist a job record and update the hash registry when appropriate.

        Duplicate job records are persisted too, but the registry continues to point
        to the original canonical document ID for that SHA256 hash.
        """
        try:
            await asyncio.to_thread(self._create_or_replace_job_sync, job_record)
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise RepositoryError(
                "Failed to persist ingestion job record.",
                context={"document_id": job_record.document_id},
            ) from exc

    async def update_stage_status(
        self,
        *,
        document_id: str,
        stage_name: IngestionStageName,
        status: StageExecutionStatus,
        warnings: list[StageWarning] | None = None,
        details: dict[str, Any] | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> IngestionJobRecord:
        """Update the stored status for a single stage and return the updated job record."""
        try:
            return await asyncio.to_thread(
                self._update_stage_status_sync,
                document_id,
                stage_name,
                status,
                warnings or [],
                details or {},
                started_at,
                completed_at,
            )
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise RepositoryError(
                "Failed to update stage status.",
                context={"document_id": document_id, "stage_name": stage_name.value},
            ) from exc

    async def mark_job_failed(self, *, document_id: str, reason: str) -> IngestionJobRecord:
        """Mark a persisted job as failed."""
        job = await self.get_job_by_document_id(document_id)
        if job is None:
            raise RepositoryError(
                "Cannot mark a non-existent ingestion job as failed.",
                context={"document_id": document_id},
            )

        job.status = IngestionJobStatus.FAILED
        job.updated_at = datetime.now(UTC)
        job.source_metadata["failure_reason"] = reason
        await self.create_or_replace_job(job)
        return job

    async def mark_job_completed(self, *, document_id: str) -> IngestionJobRecord:
        """Mark a persisted job as completed."""
        job = await self.get_job_by_document_id(document_id)
        if job is None:
            raise RepositoryError(
                "Cannot mark a non-existent ingestion job as completed.",
                context={"document_id": document_id},
            )

        job.status = IngestionJobStatus.COMPLETED
        job.updated_at = datetime.now(UTC)
        await self.create_or_replace_job(job)
        return job

    # ---------------------------------------------------------------------
    # Internal sync helpers
    # ---------------------------------------------------------------------

    def _initialize_sync(self) -> None:
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        self._base_dir.mkdir(parents=True, exist_ok=True)

        if not self._hash_registry_path.exists():
            self._hash_registry_path.write_bytes(orjson.dumps({}))

    def _get_job_by_document_id_sync(self, document_id: str) -> IngestionJobRecord | None:
        self._initialize_sync()
        job_path = self._jobs_dir / f"{document_id}.json"
        if not job_path.exists():
            return None

        payload = orjson.loads(job_path.read_bytes())
        return IngestionJobRecord.model_validate(payload)

    def _get_job_by_sha256_hash_sync(self, sha256_hash: str) -> IngestionJobRecord | None:
        self._initialize_sync()
        registry = self._read_hash_registry_sync()
        canonical_document_id = registry.get(sha256_hash.lower())
        if canonical_document_id is None:
            return None

        return self._get_job_by_document_id_sync(canonical_document_id)

    def _create_or_replace_job_sync(self, job_record: IngestionJobRecord) -> None:
        self._initialize_sync()
        job_path = self._jobs_dir / f"{job_record.document_id}.json"
        payload = job_record.model_dump(mode="json")
        job_path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))

        registry = self._read_hash_registry_sync()

        if not job_record.is_duplicate:
            registry[job_record.sha256_hash] = job_record.document_id
        elif job_record.duplicate_of_document_id and job_record.sha256_hash not in registry:
            registry[job_record.sha256_hash] = job_record.duplicate_of_document_id

        self._hash_registry_path.write_bytes(
            orjson.dumps(registry, option=orjson.OPT_INDENT_2)
        )

    def _update_stage_status_sync(
        self,
        document_id: str,
        stage_name: IngestionStageName,
        status: StageExecutionStatus,
        warnings: list[StageWarning],
        details: dict[str, Any],
        started_at: datetime | None,
        completed_at: datetime | None,
    ) -> IngestionJobRecord:
        job = self._get_job_by_document_id_sync(document_id)
        if job is None:
            raise RepositoryError(
                "Cannot update stage status for a non-existent ingestion job.",
                context={"document_id": document_id, "stage_name": stage_name.value},
            )

        existing_record = job.stage_statuses.get(stage_name.value)
        stage_record = StageStatusRecord(
            stage_name=stage_name,
            status=status,
            started_at=started_at or (existing_record.started_at if existing_record else None),
            completed_at=completed_at,
            warnings=warnings,
            details=details,
        )

        job.stage_statuses[stage_name.value] = stage_record
        job.current_stage = stage_name
        job.updated_at = datetime.now(UTC)

        self._create_or_replace_job_sync(job)
        return job

    def _read_hash_registry_sync(self) -> dict[str, str]:
        self._initialize_sync()
        return orjson.loads(self._hash_registry_path.read_bytes())