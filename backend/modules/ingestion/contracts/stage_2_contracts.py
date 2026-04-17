"""
Stage 2 contracts for ingestion: document parsing and markdown enrichment.

Stage 2 responsibilities:
- parse source PDF/DOCX into markdown using Azure Document Intelligence
- persist raw markdown
- build deterministic registries for images, hyperlinks, and tables
- clean headers, footers, and whitespace
- detect embedded objects as warnings
- emit a deterministic parse quality report
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.ingestion.contracts.stage_1_contracts import (
    BlobArtifactReference,
    Stage1Output,
    StageWarning,
)


class ParseQualityTier(str, Enum):
    """High-level quality tier for parsed markdown."""

    GOOD = "good"
    DEGRADED = "degraded"


class AssetType(str, Enum):
    """Supported asset types identified during Stage 2 enrichment."""

    IMAGE = "IMAGE"
    EMBEDDED_OBJECT = "EMBEDDED_OBJECT"


class AssetClassification(str, Enum):
    """
    Asset classification labels carried through the ingestion pipeline.

    Stage 2 starts all extracted assets as UNKNOWN.
    Stage 4 updates image assets with deterministic or classifier-backed labels.
    """

    UNKNOWN = "UNKNOWN"
    NON_DIAGRAM = "NON_DIAGRAM"
    FLOWCHART = "FLOWCHART"
    ARCHITECTURE = "ARCHITECTURE"
    SEQUENCE = "SEQUENCE"
    GENERIC_DIAGRAM = "GENERIC_DIAGRAM"



class AssetRecord(BaseModel):
    """Represents an extracted image or embedded-object-style asset."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(..., min_length=1)
    asset_type: AssetType
    classification: AssetClassification = AssetClassification.UNKNOWN
    alt_text: str | None = None
    source_reference: str | None = None
    placeholder: str = Field(..., min_length=1)
    occurrence_index: int = Field(..., ge=0)
    line_number: int | None = Field(default=None, ge=1)


class AssetRegistry(BaseModel):
    """Collection of extracted document assets."""

    model_config = ConfigDict(extra="forbid")

    assets: list[AssetRecord] = Field(default_factory=list)

    @property
    def image_count(self) -> int:
        return sum(1 for asset in self.assets if asset.asset_type == AssetType.IMAGE)

    @property
    def embedded_object_count(self) -> int:
        return sum(1 for asset in self.assets if asset.asset_type == AssetType.EMBEDDED_OBJECT)


class HyperlinkRecord(BaseModel):
    """Represents a non-image markdown hyperlink."""

    model_config = ConfigDict(extra="forbid")

    hyperlink_id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    occurrence_index: int = Field(..., ge=0)
    line_number: int | None = Field(default=None, ge=1)


class HyperlinkRegistry(BaseModel):
    """Collection of extracted hyperlinks."""

    model_config = ConfigDict(extra="forbid")

    hyperlinks: list[HyperlinkRecord] = Field(default_factory=list)

    @property
    def hyperlink_count(self) -> int:
        return len(self.hyperlinks)


class TableRecord(BaseModel):
    """Represents a markdown table block extracted from parsed content."""

    model_config = ConfigDict(extra="forbid")

    table_id: str = Field(..., min_length=1)
    markdown: str = Field(..., min_length=1)
    start_line: int = Field(..., ge=1)
    end_line: int = Field(..., ge=1)
    row_count: int = Field(..., ge=0)
    column_count: int = Field(..., ge=0)


class TableRegistry(BaseModel):
    """Collection of extracted markdown tables."""

    model_config = ConfigDict(extra="forbid")

    tables: list[TableRecord] = Field(default_factory=list)

    @property
    def table_count(self) -> int:
        return len(self.tables)


class ParseQualityReport(BaseModel):
    """Deterministic parse quality summary for Stage 2 outputs."""

    model_config = ConfigDict(extra="forbid")

    heading_count: int = Field(..., ge=0)
    image_count: int = Field(..., ge=0)
    table_count: int = Field(..., ge=0)
    hyperlink_count: int = Field(..., ge=0)
    estimated_tokens: int = Field(..., ge=0)
    quality_tier: ParseQualityTier
    embedded_object_detected: bool = False
    warnings: list[StageWarning] = Field(default_factory=list)


class Stage2Metrics(BaseModel):
    """Metrics emitted by Stage 2 for tracing and debugging."""

    model_config = ConfigDict(extra="forbid")

    parse_duration_ms: float = Field(..., ge=0)
    enrichment_duration_ms: float = Field(..., ge=0)
    persistence_duration_ms: float = Field(..., ge=0)
    total_duration_ms: float = Field(..., ge=0)


class Stage2Input(BaseModel):
    """
    Input payload for Stage 2.

    This is a normalized handoff contract built from Stage 1 output so later
    stages don't need to depend directly on the full Stage1Output model.
    """

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    file_name: str = Field(..., min_length=1)
    content_type: str = Field(..., min_length=1)
    sha256_hash: str = Field(..., min_length=64, max_length=64)
    source_blob: BlobArtifactReference
    correlation_id: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    prior_warnings: list[StageWarning] = Field(default_factory=list)

    @classmethod
    def from_stage_1_output(cls, stage_1_output: Stage1Output) -> "Stage2Input":
        """Create a Stage 2 input contract from Stage 1 output."""
        return cls(
            process_id=stage_1_output.process_id,
            document_id=stage_1_output.document_id,
            file_name=stage_1_output.job_record.file_name,
            content_type=stage_1_output.job_record.content_type,
            sha256_hash=stage_1_output.sha256_hash,
            source_blob=stage_1_output.original_file,
            correlation_id=stage_1_output.job_record.correlation_id,
            source_metadata=stage_1_output.job_record.source_metadata,
            prior_warnings=stage_1_output.warnings,
        )


class Stage2Output(BaseModel):
    """Output payload for Stage 2 parsing and markdown enrichment."""

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    source_blob: BlobArtifactReference

    raw_markdown: str = Field(..., min_length=1)
    enriched_markdown: str = Field(..., min_length=1)

    raw_markdown_artifact: BlobArtifactReference
    enriched_markdown_artifact: BlobArtifactReference

    asset_registry: AssetRegistry
    hyperlink_registry: HyperlinkRegistry
    table_registry: TableRegistry
    parse_quality_report: ParseQualityReport

    asset_registry_artifact: BlobArtifactReference
    hyperlink_registry_artifact: BlobArtifactReference
    table_registry_artifact: BlobArtifactReference
    parse_quality_artifact: BlobArtifactReference

    warnings: list[StageWarning] = Field(default_factory=list)
    metrics: Stage2Metrics