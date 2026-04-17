"""
Stage 9 executor: vector indexing.

This stage:
- updates repository stage state
- executes vector indexing through IndexingService
- verifies retrieval-critical indexed-document fields exist
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.modules.ingestion.contracts.stage_1_contracts import (
    IngestionStageName,
    StageExecutionStatus,
)
from backend.modules.ingestion.contracts.stage_9_contracts import (
    Stage9Input,
    Stage9Output,
)
from backend.modules.ingestion.exceptions import IngestionError, IndexingError, StageExecutionError
from backend.modules.ingestion.repositories.ingestion_repository import IngestionRepository
from backend.modules.ingestion.services.indexing_service import IndexingService


class VectorIndexingStage:
    """Executor for Stage 9 of the ingestion pipeline."""

    def __init__(
        self,
        *,
        indexing_service: IndexingService,
        repository: IngestionRepository,
    ) -> None:
        self._indexing_service = indexing_service
        self._repository = repository

    async def run(self, request: Stage9Input) -> Stage9Output:
        """Execute Stage 9 vector indexing."""
        started_at = datetime.now(UTC)
        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.VECTOR_INDEXING,
            status=StageExecutionStatus.RUNNING,
            started_at=started_at,
        )

        try:
            result = await self._indexing_service.index_chunks(request)
            self._assert_stage_success_criteria(result)
        except IngestionError:
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.VECTOR_INDEXING,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"document_id": request.document_id, "index_name": request.index_name},
            )
            raise
        except Exception as exc:  # pragma: no cover - defensive wrapper
            await self._repository.update_stage_status(
                document_id=request.document_id,
                stage_name=IngestionStageName.VECTOR_INDEXING,
                status=StageExecutionStatus.FAILED,
                started_at=started_at,
                completed_at=datetime.now(UTC),
                details={"document_id": request.document_id, "index_name": request.index_name},
            )
            raise StageExecutionError(
                "Stage 9 vector indexing failed unexpectedly.",
                context={"document_id": request.document_id, "index_name": request.index_name},
            ) from exc

        await self._repository.update_stage_status(
            document_id=request.document_id,
            stage_name=IngestionStageName.VECTOR_INDEXING,
            status=StageExecutionStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            warnings=result.warnings,
            details={
                "index_name": result.index_name,
                "total_documents_built": result.metrics.total_documents_built,
                "total_documents_indexed": result.metrics.total_documents_indexed,
                "count_mismatch_detected": result.metrics.count_mismatch_detected,
            },
        )

        return result

    def _assert_stage_success_criteria(self, result: Stage9Output) -> None:
        """
        Verify the locked Stage 9 success criteria.

        Required:
        - every indexed document includes section_id
        - chunk_index_in_section is assigned
        - requirement_ids field exists
        """
        if not result.indexed_documents:
            raise IndexingError(
                "Stage 9 produced no indexed search documents.",
                context={"document_id": result.document_id, "index_name": result.index_name},
            )

        for document in result.indexed_documents:
            if not document.section_id:
                raise IndexingError(
                    "Indexed document is missing section_id.",
                    context={"chunk_id": document.chunk_id},
                )

            if document.chunk_index_in_section < 0:
                raise IndexingError(
                    "Indexed document is missing a valid chunk_index_in_section.",
                    context={"chunk_id": document.chunk_id},
                )

            if document.requirement_ids is None:
                raise IndexingError(
                    "Indexed document must include requirement_ids, even when empty.",
                    context={"chunk_id": document.chunk_id},
                )