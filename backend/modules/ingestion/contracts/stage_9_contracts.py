"""
Stage 9 contracts for ingestion: vector indexing.

Stage 9 responsibilities:
- embed summary if available, otherwise embed raw content
- build Azure AI Search documents using the locked retrieval-aligned schema
- upsert documents idempotently into the configured index
- verify indexed-document counts
- emit indexing metrics and warnings
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.ingestion.contracts.stage_1_contracts import (
    BlobArtifactReference,
    StageWarning,
)
from backend.modules.ingestion.contracts.stage_8_contracts import (
    EnrichedChunk,
    Stage8Output,
)


class SearchDocument(BaseModel):
    """
    Azure AI Search document built from an enriched chunk.

    The fields intentionally match the locked aligned ingestion schema required
    by downstream retrieval.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    section_id: str = Field(..., min_length=1)
    document_type: str = Field(..., min_length=1)
    section_type: str = Field(..., min_length=1)

    content: str = Field(..., min_length=1)
    summary: str | None = None
    embedding: list[float] = Field(default_factory=list)

    chunk_index_in_section: int = Field(..., ge=0)
    has_table: bool = False
    has_vision_extraction: bool = False
    has_list: bool = False
    has_requirement_id: bool = False
    requirement_ids: list[str] = Field(default_factory=list)


class Stage9Metrics(BaseModel):
    """Metrics emitted by Stage 9 vector indexing."""

    model_config = ConfigDict(extra="forbid")

    total_chunks_received: int = Field(..., ge=0)
    total_documents_built: int = Field(..., ge=0)
    total_documents_indexed: int = Field(..., ge=0)
    count_mismatch_detected: bool = False
    embedding_duration_ms: float = Field(..., ge=0)
    indexing_duration_ms: float = Field(..., ge=0)
    total_duration_ms: float = Field(..., ge=0)


class Stage9Input(BaseModel):
    """Input payload for Stage 9 vector indexing."""

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    source_blob: BlobArtifactReference
    chunks: list[EnrichedChunk] = Field(default_factory=list)
    index_name: str = Field(default="sdlc_knowledge_index", min_length=1)
    prior_warnings: list[StageWarning] = Field(default_factory=list)

    @classmethod
    def from_stage_8_output(cls, stage_8_output: Stage8Output) -> "Stage9Input":
        """Create Stage 9 input from Stage 8 output."""
        return cls(
            process_id=stage_8_output.process_id,
            document_id=stage_8_output.document_id,
            source_blob=stage_8_output.source_blob,
            chunks=stage_8_output.chunks,
            prior_warnings=stage_8_output.warnings,
        )


class Stage9Output(BaseModel):
    """Output payload for Stage 9 vector indexing."""

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    source_blob: BlobArtifactReference
    index_name: str = Field(..., min_length=1)
    indexed_documents: list[SearchDocument] = Field(default_factory=list)
    warnings: list[StageWarning] = Field(default_factory=list)
    metrics: Stage9Metrics