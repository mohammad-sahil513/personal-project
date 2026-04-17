"""
Stage 1 contracts for ingestion: upload and deduplication.

This file defines the typed DTOs for the first ingestion stage:
- upload request payload
- blob artifact reference
- stage warnings and metrics
- ingestion job record
- stage output payload

The models are deliberately strict (extra='forbid') because the project is
contract-driven and later stages depend on stable, validated fields.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IngestionStageName(str, Enum):
    """Canonical stage names used across ingestion persistence and orchestration."""

    UPLOAD_AND_DEDUP = "01_upload_and_dedup"
    PARSE_DOCUMENT = "02_parse_document"
    MASK_PII = "03_mask_pii"
    CLASSIFY_IMAGES = "04_classify_images"
    VISION_EXTRACTION = "05_vision_extraction"
    SEGMENT_SECTIONS = "06_segment_sections"
    VALIDATE_OUTPUTS = "07_validate_outputs"
    SEMANTIC_CHUNKING = "08_semantic_chunking"
    VECTOR_INDEXING = "09_vector_indexing"

class IngestionJobStatus(str, Enum):
    """High-level lifecycle state for an ingestion job."""

    CREATED = "CREATED"
    IN_PROGRESS = "IN_PROGRESS"
    DUPLICATE = "DUPLICATE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class StageExecutionStatus(str, Enum):
    """Execution state for an individual pipeline stage."""

    NOT_STARTED = "NOT_STARTED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class SupportedDocumentExtension(str, Enum):
    """Supported document extensions for the PoC ingestion scope."""

    PDF = ".pdf"
    DOCX = ".docx"


class StageWarning(BaseModel):
    """Represents a non-fatal issue or informational warning emitted by a stage."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(..., min_length=1)
    message: str = Field(..., min_length=1)
    details: dict[str, Any] = Field(default_factory=dict)


class BlobArtifactReference(BaseModel):
    """
    Reference to an artifact persisted in the shared Azure Blob container.

    The system uses a single shared Blob container, and all paths must stay
    under the configured root prefix (e.g. sahil_storage/).
    """

    model_config = ConfigDict(extra="forbid")

    container_name: str = Field(..., min_length=1)
    blob_path: str = Field(..., min_length=1)
    content_type: str = Field(..., min_length=1)
    size_bytes: int = Field(..., ge=0)
    etag: str | None = None
    version_id: str | None = None
    url: str | None = None

    @field_validator("blob_path")
    @classmethod
    def validate_blob_path(cls, value: str) -> str:
        if not value.startswith("sahil_storage/"):
            raise ValueError("blob_path must start with 'sahil_storage/'")
        return value


class StageStatusRecord(BaseModel):
    """Persistent execution metadata for a single pipeline stage."""

    model_config = ConfigDict(extra="forbid")

    stage_name: IngestionStageName
    status: StageExecutionStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    warnings: list[StageWarning] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class Stage1Metrics(BaseModel):
    """Metrics emitted by Stage 1 for debugging and observability."""

    model_config = ConfigDict(extra="forbid")

    file_size_bytes: int = Field(..., ge=0)
    upload_duration_ms: float = Field(..., ge=0)
    duplicate_lookup_duration_ms: float = Field(..., ge=0)
    total_duration_ms: float = Field(..., ge=0)


class Stage1Input(BaseModel):
    """Input payload for Stage 1 upload and deduplication."""

    model_config = ConfigDict(extra="forbid")

    file_name: str = Field(..., min_length=1)
    content_type: str = Field(..., min_length=1)
    file_bytes: bytes = Field(..., min_length=1)
    initiated_by: str | None = None
    correlation_id: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("file_name must not be blank")

        if "." not in normalized:
            raise ValueError("file_name must include a file extension")

        return normalized

    @property
    def file_extension(self) -> str:
        return f".{self.file_name.rsplit('.', maxsplit=1)[-1].lower()}"


class IngestionJobRecord(BaseModel):
    """
    Persistent job record stored by the ingestion repository.

    This record is the primary metadata object for tracking ingestion progress
    in the no-database initial architecture.
    """

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    file_name: str = Field(..., min_length=1)
    content_type: str = Field(..., min_length=1)
    sha256_hash: str = Field(..., min_length=64, max_length=64)
    source_blob: BlobArtifactReference
    status: IngestionJobStatus
    current_stage: IngestionStageName
    is_duplicate: bool = False
    duplicate_of_document_id: str | None = None
    initiated_by: str | None = None
    correlation_id: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    stage_statuses: dict[str, StageStatusRecord] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("sha256_hash")
    @classmethod
    def validate_sha256_hash(cls, value: str) -> str:
        normalized = value.strip().lower()
        if len(normalized) != 64:
            raise ValueError("sha256_hash must be a 64-character hexadecimal digest")
        return normalized


class Stage1Output(BaseModel):
    """Output payload for Stage 1 upload and deduplication."""

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    sha256_hash: str = Field(..., min_length=64, max_length=64)
    original_file: BlobArtifactReference
    is_duplicate: bool = False
    duplicate_of_document_id: str | None = None
    job_record: IngestionJobRecord
    warnings: list[StageWarning] = Field(default_factory=list)
    metrics: Stage1Metrics