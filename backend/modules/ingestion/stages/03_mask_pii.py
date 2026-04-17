"""
Stage 3 executor: PII detection and selective masking.

This stage:
- updates repository stage status
- delegates PII processing to PiiService
- returns a typed Stage3Output
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.modules.ingestion.contracts.stage_1_contracts import (
    IngestionStageName,
    StageExecutionStatus,
)
from backend.modules.ingestion.contracts.stage_3_contracts import (
    Stage3Input,
    Stage3Output,
)
from backend.modules.ingestion.exceptions import IngestionError, StageExecutionError
from backend.modules.ingestion.repositories.ingestion_repository import IngestionRepository
from backend.modules.ingestion.services.pii_service import PiiService


class MaskPiiStage:
    """Executor for Stage 3 of the ingestion pipeline."""

    def __init__(
        self,
        *,
        pii_service: PiiService,
        repository: IngestionRepository,
    ) -> None:
        self._pii_service = pii_service
        self._repository = repository

    async def run(self, request: Stage3Input) -> Stage3Output:
        """Execute Stage 3 selective masking."""
        started_at = datetime.now(UTC)
        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.MASK_PII,
            status=StageExecutionStatus.RUNNING,
            started_at=started_at,
        )

        try:
            result = await self._pii_service.process_pii(request)
        except IngestionError:
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.MASK_PII,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"document_id": request.document_id},
            )
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.MASK_PII,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"document_id": request.document_id},
            )
            raise StageExecutionError(
                "Stage 3 PII masking failed unexpectedly.",
                context={"document_id": request.document_id},
            ) from exc

        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.MASK_PII,
            status=StageExecutionStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            warnings=result.warnings,
            details={
                "total_candidates_detected": result.metrics.total_candidates_detected,
                "total_candidates_masked": result.metrics.total_candidates_masked,
                "total_candidates_kept": result.metrics.total_candidates_kept,
                "secure_mapping_artifact": (
                    result.secure_mapping_artifact.blob_path
                    if result.secure_mapping_artifact
                    else None
                ),
            },
        )

        return result
