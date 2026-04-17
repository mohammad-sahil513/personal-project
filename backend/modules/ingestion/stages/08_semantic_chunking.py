"""
Stage 8 executor: semantic chunking.

This stage:
- updates repository stage status
- runs deterministic semantic chunking
- verifies retrieval-critical success conditions
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.modules.ingestion.contracts.stage_1_contracts import (
    IngestionStageName,
    StageExecutionStatus,
)
from backend.modules.ingestion.contracts.stage_8_contracts import (
    Stage8Input,
    Stage8Output,
)
from backend.modules.ingestion.exceptions import ChunkingError, IngestionError, StageExecutionError
from backend.modules.ingestion.repositories.ingestion_repository import IngestionRepository
from backend.modules.ingestion.services.chunking_service import ChunkingService


class SemanticChunkingStage:
    """Executor for Stage 8 of the ingestion pipeline."""

    def __init__(
        self,
        *,
        chunking_service: ChunkingService,
        repository: IngestionRepository,
    ) -> None:
        self._chunking_service = chunking_service
        self._repository = repository

    async def run(self, request: Stage8Input) -> Stage8Output:
        """Execute Stage 8 semantic chunking."""
        started_at = datetime.now(UTC)
        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.SEMANTIC_CHUNKING,
            status=StageExecutionStatus.RUNNING,
            started_at=started_at,
        )

        try:
            result = self._chunking_service.chunk_document(request)
            self._assert_stage_success_criteria(result)
        except IngestionError:
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.SEMANTIC_CHUNKING,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"document_id": request.document_id},
            )
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.SEMANTIC_CHUNKING,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"document_id": request.document_id},
            )
            raise StageExecutionError(
                "Stage 8 semantic chunking failed unexpectedly.",
                context={"document_id": request.document_id},
            ) from exc

        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.SEMANTIC_CHUNKING,
            status=StageExecutionStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            warnings=result.warnings,
            details={
                "total_chunks_created": result.metrics.total_chunks_created,
                "sections_with_forced_summary": result.metrics.sections_with_forced_summary,
                "merged_fragment_count": result.metrics.merged_fragment_count,
                "forced_split_count": result.metrics.forced_split_count,
            },
        )

        return result

    def _assert_stage_success_criteria(self, result: Stage8Output) -> None:
        """
        Verify the locked Stage 8 success criteria.

        Required:
        - every chunk has section_id
        - chunk_index_in_section is assigned
        - every section has at least one summary-backed representation
        """
        if not result.chunks:
            raise ChunkingError(
                "Stage 8 produced no chunks.",
                context={"document_id": result.document_id},
            )

        section_summary_coverage: dict[str, bool] = {}

        for chunk in result.chunks:
            if not chunk.section_id:
                raise ChunkingError(
                    "Chunk is missing section_id.",
                    context={"chunk_id": chunk.chunk_id},
                )

            if chunk.chunk_index_in_section < 0:
                raise ChunkingError(
                    "Chunk is missing a valid chunk_index_in_section.",
                    context={"chunk_id": chunk.chunk_id},
                )

            current_coverage = section_summary_coverage.get(chunk.section_id, False)
            section_summary_coverage[chunk.section_id] = current_coverage or bool(chunk.summary)

        uncovered_sections = [section_id for section_id, covered in section_summary_coverage.items() if not covered]
        if uncovered_sections:
            raise ChunkingError(
                "Every section must have at least one summary-backed representation.",
                context={"uncovered_sections": uncovered_sections},
            )
