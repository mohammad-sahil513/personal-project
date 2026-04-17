"""
Indexing service for Stage 9.

This service:
- selects embedding text (summary first, fallback to content)
- generates vector embeddings
- builds retrieval-aligned Azure AI Search documents
- upserts documents into the configured search index
- verifies count alignment between chunks and indexed documents
"""

from __future__ import annotations

from time import perf_counter
from typing import Protocol

from backend.modules.ingestion.contracts.stage_1_contracts import StageWarning
from backend.modules.ingestion.contracts.stage_8_contracts import EnrichedChunk
from backend.modules.ingestion.contracts.stage_9_contracts import (
    SearchDocument,
    Stage9Input,
    Stage9Metrics,
    Stage9Output,
)
from backend.modules.ingestion.exceptions import IndexingError


class EmbeddingClientProtocol(Protocol):
    """Minimal embedding client contract for Stage 9."""

    async def embed_texts(self, *, texts: list[str]) -> list[list[float]]:
        """Embed the provided texts and return vectors in the same order."""
        ...


class SearchClientProtocol(Protocol):
    """Minimal search client contract for Stage 9."""

    async def upsert_documents(
        self,
        *,
        index_name: str,
        documents: list[dict],
    ) -> int:
        """
        Upsert documents into Azure AI Search and return the count acknowledged
        by the client wrapper.
        """
        ...


class IndexingService:
    """Service that executes Stage 9 vector indexing."""

    def __init__(
        self,
        *,
        embedding_client: EmbeddingClientProtocol,
        search_client: SearchClientProtocol,
    ) -> None:
        self._embedding_client = embedding_client
        self._search_client = search_client

    async def index_chunks(self, request: Stage9Input) -> Stage9Output:
        """Build embeddings, transform chunks into search documents, and upsert them."""
        if not request.chunks:
            raise IndexingError(
                "Stage 9 cannot proceed because no chunks were provided for indexing.",
                context={"document_id": request.document_id},
            )

        total_start = perf_counter()

        embedding_texts = [self._select_embedding_text(chunk) for chunk in request.chunks]

        embedding_start = perf_counter()
        embeddings = await self._embedding_client.embed_texts(texts=embedding_texts)
        embedding_duration_ms = (perf_counter() - embedding_start) * 1000

        if len(embeddings) != len(request.chunks):
            raise IndexingError(
                "Embedding response count does not match the number of chunks.",
                context={
                    "chunk_count": len(request.chunks),
                    "embedding_count": len(embeddings),
                },
            )

        search_documents = self._build_search_documents(
            chunks=request.chunks,
            embeddings=embeddings,
        )

        indexing_start = perf_counter()
        acknowledged_count = await self._search_client.upsert_documents(
            index_name=request.index_name,
            documents=[document.model_dump(mode="json") for document in search_documents],
        )
        indexing_duration_ms = (perf_counter() - indexing_start) * 1000

        warnings = list(request.prior_warnings)
        count_mismatch_detected = acknowledged_count != len(search_documents)
        if count_mismatch_detected:
            warnings.append(
                StageWarning(
                    code="INDEX_DOCUMENT_COUNT_MISMATCH",
                    message="The acknowledged indexed-document count did not match the number of built search documents.",
                    details={
                        "expected_count": len(search_documents),
                        "acknowledged_count": acknowledged_count,
                        "index_name": request.index_name,
                    },
                )
            )

        total_duration_ms = (perf_counter() - total_start) * 1000
        metrics = Stage9Metrics(
            total_chunks_received=len(request.chunks),
            total_documents_built=len(search_documents),
            total_documents_indexed=acknowledged_count,
            count_mismatch_detected=count_mismatch_detected,
            embedding_duration_ms=round(embedding_duration_ms, 3),
            indexing_duration_ms=round(indexing_duration_ms, 3),
            total_duration_ms=round(total_duration_ms, 3),
        )

        return Stage9Output(
            process_id=request.process_id,
            document_id=request.document_id,
            source_blob=request.source_blob,
            index_name=request.index_name,
            indexed_documents=search_documents,
            warnings=warnings,
            metrics=metrics,
        )

    def _build_search_documents(
        self,
        *,
        chunks: list[EnrichedChunk],
        embeddings: list[list[float]],
    ) -> list[SearchDocument]:
        """Transform enriched chunks plus embeddings into Azure AI Search documents."""
        search_documents: list[SearchDocument] = []

        for chunk, embedding in zip(chunks, embeddings, strict=True):
            search_documents.append(
                SearchDocument(
                    chunk_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    section_id=chunk.section_id,
                    document_type=chunk.document_type,
                    section_type=chunk.section_type,
                    content=chunk.content,
                    summary=chunk.summary,
                    embedding=embedding,
                    chunk_index_in_section=chunk.chunk_index_in_section,
                    has_table=chunk.has_table,
                    has_vision_extraction=chunk.has_vision_extraction,
                    has_list=chunk.has_list,
                    has_requirement_id=chunk.has_requirement_id,
                    requirement_ids=chunk.requirement_ids,
                )
            )

        return search_documents

    @staticmethod
    def _select_embedding_text(chunk: EnrichedChunk) -> str:
        """
        Select the text to embed using the locked Stage 9 rule:
        - embed summary if available
        - otherwise embed raw content
        """
        if chunk.summary and chunk.summary.strip():
            return chunk.summary.strip()

        return chunk.content.strip()