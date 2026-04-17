"""
Stage 1 executor: upload and deduplication.

This stage is intentionally thin:
- it accepts a validated Stage1Input DTO
- delegates business logic to UploadService
- wraps unexpected failures in a stage-specific domain exception
"""

from __future__ import annotations

from backend.modules.ingestion.contracts.stage_1_contracts import Stage1Input, Stage1Output
from backend.modules.ingestion.exceptions import IngestionError, StageExecutionError
from backend.modules.ingestion.services.upload_service import UploadService


class UploadAndDedupStage:
    """Executor for Stage 1 of the ingestion pipeline."""

    def __init__(self, upload_service: UploadService) -> None:
        self._upload_service = upload_service

    async def run(self, request: Stage1Input) -> Stage1Output:
        """Execute Stage 1 and return a strongly typed Stage1Output payload."""
        try:
            return await self._upload_service.upload_and_deduplicate(request)
        except IngestionError:
            # Re-raise domain exceptions unchanged so callers can make stage-aware decisions.
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise StageExecutionError(
                "Stage 1 upload and deduplication failed unexpectedly.",
                context={"file_name": request.file_name},
            ) from exc