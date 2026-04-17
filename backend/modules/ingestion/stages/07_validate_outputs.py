"""
Stage 7 executor: validation.

This stage:
- updates repository stage status
- runs deterministic validation using ValidationService
- returns a typed Stage7Output
- marks the stage as COMPLETED when validation runs successfully,
  even if the validation result contains global-failure issues
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.modules.ingestion.contracts.stage_1_contracts import (
    IngestionStageName,
    StageExecutionStatus,
)
from backend.modules.ingestion.contracts.stage_7_contracts import (
    Stage7Input,
    Stage7Output,
)
from backend.modules.ingestion.exceptions import IngestionError, StageExecutionError
from backend.modules.ingestion.repositories.ingestion_repository import IngestionRepository
from backend.modules.ingestion.services.validation_service import ValidationService


class ValidateOutputsStage:
    """Executor for Stage 7 of the ingestion pipeline."""

    def __init__(
        self,
        *,
        validation_service: ValidationService,
        repository: IngestionRepository,
    ) -> None:
        self._validation_service = validation_service
        self._repository = repository

    async def run(self, request: Stage7Input) -> Stage7Output:
        """Execute Stage 7 validation."""
        started_at = datetime.now(UTC)
        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.VALIDATE_OUTPUTS,
            status=StageExecutionStatus.RUNNING,
            started_at=started_at,
        )

        try:
            result = self._validation_service.validate(request)
        except IngestionError:
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.VALIDATE_OUTPUTS,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"document_id": request.document_id},
            )
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.VALIDATE_OUTPUTS,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"document_id": request.document_id},
            )
            raise StageExecutionError(
                "Stage 7 validation failed unexpectedly.",
                context={"document_id": request.document_id},
            ) from exc

        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.VALIDATE_OUTPUTS,
            status=StageExecutionStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            warnings=result.warnings,
            details={
                "total_issues": result.summary.total_issues,
                "error_count": result.summary.error_count,
                "warning_count": result.summary.warning_count,
                "has_global_failure": result.summary.has_global_failure,
                "can_proceed_to_chunking": result.summary.can_proceed_to_chunking,
            },
        )

        return result