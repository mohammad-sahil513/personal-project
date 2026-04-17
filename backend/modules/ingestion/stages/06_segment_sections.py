"""
Stage 6 executor: deterministic section segmentation.

This stage:
- updates repository stage state
- delegates segmentation logic to SegmentationService
- returns a strongly typed Stage6Output
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.modules.ingestion.contracts.stage_1_contracts import (
    IngestionStageName,
    StageExecutionStatus,
)
from backend.modules.ingestion.contracts.stage_6_contracts import (
    Stage6Input,
    Stage6Output,
)
from backend.modules.ingestion.exceptions import IngestionError, StageExecutionError
from backend.modules.ingestion.repositories.ingestion_repository import IngestionRepository
from backend.modules.ingestion.services.segmentation_service import SegmentationService


class SegmentSectionsStage:
    """Executor for Stage 6 of the ingestion pipeline."""

    def __init__(
        self,
        *,
        segmentation_service: SegmentationService,
        repository: IngestionRepository,
    ) -> None:
        self._segmentation_service = segmentation_service
        self._repository = repository

    async def run(self, request: Stage6Input) -> Stage6Output:
        """Execute Stage 6 segmentation."""
        started_at = datetime.now(UTC)
        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.SEGMENT_SECTIONS,
            status=StageExecutionStatus.RUNNING,
            started_at=started_at,
        )

        try:
            result = self._segmentation_service.segment_document(request)
        except IngestionError:
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.SEGMENT_SECTIONS,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"document_id": request.document_id},
            )
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.SEGMENT_SECTIONS,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"document_id": request.document_id},
            )
            raise StageExecutionError(
                "Stage 6 section segmentation failed unexpectedly.",
                context={"document_id": request.document_id},
            ) from exc

        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.SEGMENT_SECTIONS,
            status=StageExecutionStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            warnings=result.warnings,
            details={
                "total_sections": result.metrics.total_sections,
                "heading_matched_sections": result.metrics.heading_matched_sections,
                "synthetic_sections": result.metrics.synthetic_sections,
            },
        )

        return result