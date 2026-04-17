"""
Stage 4 executor: image classification.

This stage:
- updates repository stage state
- delegates image classification to ImageClassificationService
- returns a typed Stage4Output
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.modules.ingestion.contracts.stage_1_contracts import (
    IngestionStageName,
    StageExecutionStatus,
)
from backend.modules.ingestion.contracts.stage_4_contracts import (
    Stage4Input,
    Stage4Output,
)
from backend.modules.ingestion.exceptions import IngestionError, StageExecutionError
from backend.modules.ingestion.repositories.ingestion_repository import IngestionRepository
from backend.modules.ingestion.services.image_classification_service import ImageClassificationService


class ClassifyImagesStage:
    """Executor for Stage 4 of the ingestion pipeline."""

    def __init__(
        self,
        *,
        image_classification_service: ImageClassificationService,
        repository: IngestionRepository,
    ) -> None:
        self._image_classification_service = image_classification_service
        self._repository = repository

    async def run(self, request: Stage4Input) -> Stage4Output:
        """Execute Stage 4 image classification."""
        started_at = datetime.now(UTC)
        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.CLASSIFY_IMAGES,
            status=StageExecutionStatus.RUNNING,
            started_at=started_at,
        )

        try:
            result = await self._image_classification_service.classify_images(request)
        except IngestionError:
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.CLASSIFY_IMAGES,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"document_id": request.document_id},
            )
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.CLASSIFY_IMAGES,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"document_id": request.document_id},
            )
            raise StageExecutionError(
                "Stage 4 image classification failed unexpectedly.",
                context={"document_id": request.document_id},
            ) from exc

        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.CLASSIFY_IMAGES,
            status=StageExecutionStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            warnings=result.warnings,
            details={
                "total_assets_received": result.metrics.total_assets_received,
                "total_image_assets": result.metrics.total_image_assets,
                "deterministic_classification_count": result.metrics.deterministic_classification_count,
                "ambiguous_classification_count": result.metrics.ambiguous_classification_count,
                "total_vision_eligible_assets": result.metrics.total_vision_eligible_assets,
            },
        )

        return result
