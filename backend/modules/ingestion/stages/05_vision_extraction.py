"""
Stage 5 executor: selective vision extraction.

This stage:
- updates repository stage state
- delegates selective vision extraction to VisionExtractionService
- returns a typed Stage5Output
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.modules.ingestion.contracts.stage_1_contracts import (
    IngestionStageName,
    StageExecutionStatus,
)
from backend.modules.ingestion.contracts.stage_5_contracts import (
    Stage5Input,
    Stage5Output,
)
from backend.modules.ingestion.exceptions import IngestionError, StageExecutionError
from backend.modules.ingestion.repositories.ingestion_repository import IngestionRepository
from backend.modules.ingestion.services.vision_extraction_service import VisionExtractionService


class VisionExtractionStage:
    """Executor for Stage 5 of the ingestion pipeline."""

    def __init__(
        self,
        *,
        vision_extraction_service: VisionExtractionService,
        repository: IngestionRepository,
    ) -> None:
        self._vision_extraction_service = vision_extraction_service
        self._repository = repository

    async def run(self, request: Stage5Input) -> Stage5Output:
        """Execute Stage 5 selective vision extraction."""
        started_at = datetime.now(UTC)
        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.VISION_EXTRACTION,
            status=StageExecutionStatus.RUNNING,
            started_at=started_at,
        )

        try:
            result = await self._vision_extraction_service.extract_vision(request)
        except IngestionError:
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.VISION_EXTRACTION,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"document_id": request.document_id},
            )
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.VISION_EXTRACTION,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"document_id": request.document_id},
            )
            raise StageExecutionError(
                "Stage 5 vision extraction failed unexpectedly.",
                context={"document_id": request.document_id},
            ) from exc

        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.VISION_EXTRACTION,
            status=StageExecutionStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            warnings=result.warnings,
            details={
                "total_vision_eligible_assets": result.metrics.total_vision_eligible_assets,
                "total_vision_calls_attempted": result.metrics.total_vision_calls_attempted,
                "total_extractions_completed": result.metrics.total_extractions_completed,
                "total_skipped_by_cap": result.metrics.total_skipped_by_cap,
                "total_failures": result.metrics.total_failures,
            },
        )

        return result
