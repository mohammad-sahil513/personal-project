"""
Stage 8 contracts for ingestion: semantic chunking.

Stage 8 responsibilities:
- build chunk containers per segmented section
- preserve atomic blocks (tables, vision blocks, code fences, requirement blocks, nested lists)
- attach retrieval-critical metadata to each chunk
- generate chunk summaries with section-level summary coverage guarantees
- emit chunking warnings for downstream observability and debugging
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.ingestion.contracts.stage_1_contracts import (
    BlobArtifactReference,
    StageWarning,
)
from backend.modules.ingestion.contracts.stage_6_contracts import (
    SegmentedSection,
)
from backend.modules.ingestion.contracts.stage_7_contracts import (
    Stage7Output,
    ValidationSummary,
)


class ChunkWarningCode(str, Enum):
    """Locked warning codes for Stage 8 semantic chunking."""

    OVERSIZED_CHUNK = "OVERSIZED_CHUNK"
    FORCED_SPLIT = "FORCED_SPLIT"
    OVERSIZED_TABLE_CHUNK = "OVERSIZED_TABLE_CHUNK"
    CHUNK_FRAGMENT_MERGED = "CHUNK_FRAGMENT_MERGED"
    SUMMARY_SKIPPED = "SUMMARY_SKIPPED"
    SECTION_SUMMARY_FORCED = "SECTION_SUMMARY_FORCED"
    REQUIREMENT_IDS_EXTRACTED_EMPTY = "REQUIREMENT_IDS_EXTRACTED_EMPTY"


class ChunkWarning(BaseModel):
    """Represents a single warning emitted during chunk generation."""

    model_config = ConfigDict(extra="forbid")

    code: ChunkWarningCode
    message: str = Field(..., min_length=1)
    section_id: str = Field(..., min_length=1)
    chunk_id: str | None = None
    details: dict[str, object] = Field(default_factory=dict)


class EnrichedChunk(BaseModel):
    """
    Retrieval-aligned chunk produced by Stage 8.

    These fields intentionally match the locked ingestion contract that Stage 9
    later transforms into Azure AI Search documents.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    section_id: str = Field(..., min_length=1)
    section_type: str = Field(..., min_length=1)
    chunk_index_in_section: int = Field(..., ge=0)
    content: str = Field(..., min_length=1)
    summary: str | None = None
    estimated_tokens: int = Field(..., ge=0)

    has_table: bool = False
    has_vision_extraction: bool = False
    has_list: bool = False
    has_requirement_id: bool = False
    requirement_ids: list[str] = Field(default_factory=list)

    document_type: Literal["SOURCE"] = "SOURCE"
    chunk_warnings: list[ChunkWarning] = Field(default_factory=list)


class Stage8Metrics(BaseModel):
    """Metrics emitted by Stage 8 semantic chunking."""

    model_config = ConfigDict(extra="forbid")

    total_sections_processed: int = Field(..., ge=0)
    total_chunks_created: int = Field(..., ge=0)
    sections_with_forced_summary: int = Field(..., ge=0)
    merged_fragment_count: int = Field(..., ge=0)
    forced_split_count: int = Field(..., ge=0)
    total_duration_ms: float = Field(..., ge=0)


class Stage8Input(BaseModel):
    """
    Input payload for Stage 8 semantic chunking.

    Stage 8 should only proceed if Stage 7 validation allows progression to chunking.
    """

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    source_blob: BlobArtifactReference
    sections: list[SegmentedSection] = Field(default_factory=list)
    validation_summary: ValidationSummary
    prior_warnings: list[StageWarning] = Field(default_factory=list)

    @classmethod
    def from_stage_7_output(cls, stage_7_output: Stage7Output) -> "Stage8Input":
        """Create Stage 8 input from Stage 7 output."""
        return cls(
            process_id=stage_7_output.process_id,
            document_id=stage_7_output.document_id,
            source_blob=stage_7_output.source_blob,
            sections=stage_7_output.sections,
            validation_summary=stage_7_output.summary,
            prior_warnings=stage_7_output.warnings,
        )


class Stage8Output(BaseModel):
    """Output payload for Stage 8 semantic chunking."""

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    source_blob: BlobArtifactReference
    chunks: list[EnrichedChunk] = Field(default_factory=list)
    warnings: list[StageWarning] = Field(default_factory=list)
    metrics: Stage8Metrics