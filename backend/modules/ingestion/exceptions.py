"""
Domain exceptions for the ingestion module.

These exceptions intentionally keep domain failures readable and structured.
They can later be wrapped by API handlers or orchestration layers without
losing ingestion-specific context such as process IDs, document IDs, or
stage-level error details.
"""

from __future__ import annotations

from typing import Any


class IngestionError(Exception):
    """Base exception for all ingestion-related failures."""

    default_error_code = "INGESTION_ERROR"

    def __init__(
        self,
        message: str,
        *,
        error_code: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.default_error_code
        self.context = context or {}

    def __str__(self) -> str:
        if not self.context:
            return f"{self.error_code}: {self.message}"
        return f"{self.error_code}: {self.message} | context={self.context}"


class DuplicateDocumentError(IngestionError):
    """Raised when a document with the same content hash already exists."""

    default_error_code = "DUPLICATE_DOCUMENT"


class UnsupportedDocumentTypeError(IngestionError):
    """Raised when the uploaded file is not a supported PDF/DOCX document."""

    default_error_code = "UNSUPPORTED_DOCUMENT_TYPE"


class RepositoryError(IngestionError):
    """Raised when the ingestion repository cannot persist or read metadata."""

    default_error_code = "INGESTION_REPOSITORY_ERROR"


class BlobStorageError(IngestionError):
    """Raised when uploading or accessing Blob Storage fails."""

    default_error_code = "BLOB_STORAGE_ERROR"


class StageExecutionError(IngestionError):
    """Raised when a stage executor fails unexpectedly."""

    default_error_code = "STAGE_EXECUTION_ERROR"

class ParsingError(IngestionError):
    """Raised when document parsing or markdown enrichment fails."""

    default_error_code = "PARSING_ERROR"

class ChunkingError(IngestionError):
    """Raised when semantic chunking cannot proceed or fails unexpectedly."""

    default_error_code = "CHUNKING_ERROR"

class IndexingError(IngestionError):
    """Raised when Stage 9 vector indexing fails or cannot proceed."""

    default_error_code = "INDEXING_ERROR"

class PiiProcessingError(IngestionError):
    """Raised when Stage 3 PII detection or selective masking fails."""

    default_error_code = "PII_PROCESSING_ERROR"

class ImageClassificationError(IngestionError):
    """Raised when Stage 4 image classification fails or cannot proceed."""

    default_error_code = "IMAGE_CLASSIFICATION_ERROR"

class VisionExtractionError(IngestionError):
    """Raised when Stage 5 selective vision extraction fails or cannot proceed."""

    default_error_code = "VISION_EXTRACTION_ERROR"