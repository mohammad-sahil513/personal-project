"""
Stage 2 executor: parse document and enrich markdown.

This stage:
- normalizes the handoff from Stage 1 to Stage 2 contracts
- updates repository stage status
- delegates business logic to ParserService
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.modules.ingestion.contracts.stage_1_contracts import (
    IngestionStageName,
    StageExecutionStatus,
)
from backend.modules.ingestion.contracts.stage_2_contracts import (
    Stage2Input,
    Stage2Output,
)
from backend.modules.ingestion.exceptions import IngestionError, StageExecutionError
from backend.modules.ingestion.repositories.ingestion_repository import IngestionRepository
from backend.modules.ingestion.services.parser_service import ParserService


class ParseDocumentStage:
    """Executor for Stage 2 of the ingestion pipeline."""

    def __init__(
        self,
        *,
        parser_service: ParserService,
        repository: IngestionRepository,
    ) -> None:
        self._parser_service = parser_service
        self._repository = repository

    async def run(self, request: Stage2Input) -> Stage2Output:
        """Execute Stage 2 parsing and markdown enrichment."""
        started_at = datetime.now(UTC)
        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.PARSE_DOCUMENT,
            status=StageExecutionStatus.RUNNING,
            started_at=started_at,
        )

        try:
            result = await self._parser_service.parse_document(request)
        except IngestionError:
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.PARSE_DOCUMENT,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"file_name": request.file_name},
            )
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.PARSE_DOCUMENT,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"file_name": request.file_name},
            )
            raise StageExecutionError(
                "Stage 2 parse document failed unexpectedly.",
                context={"document_id": request.document_id, "file_name": request.file_name},
            ) from exc

        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.PARSE_DOCUMENT,
            status=StageExecutionStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            warnings=result.parse_quality_report.warnings,
            details={
                "quality_tier": result.parse_quality_report.quality_tier.value,
                "heading_count": result.parse_quality_report.heading_count,
                "image_count": result.parse_quality_report.image_count,
                "table_count": result.parse_quality_report.table_count,
                "hyperlink_count": result.parse_quality_report.hyperlink_count,
                "estimated_tokens": result.parse_quality_report.estimated_tokens,
            },
        )

        return result