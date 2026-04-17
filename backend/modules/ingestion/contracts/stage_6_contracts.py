"""
Stage 6 contracts for ingestion: deterministic section segmentation.

Stage 6 responsibilities:
- split working markdown at H1/H2 boundaries
- preserve stable section identifiers and raw content
- compute structural signals per section
- classify each section into a deterministic 10-type taxonomy

This stage is retrieval-critical because downstream retrieval depends on
`section_id` as a first-class hierarchy anchor.

Convergence note:
- before Stage 5 existed, Stage 6 could build directly from Stage 2 output
- after Stage 5, the preferred upstream input is the Stage 5 vision-enriched
  markdown path, because later chunking/indexing should reflect injected
  [VISION_EXTRACTED: ...] blocks where available
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.ingestion.contracts.stage_1_contracts import (
    BlobArtifactReference,
    StageWarning,
)
from backend.modules.ingestion.contracts.stage_2_contracts import (
    AssetRegistry,
    HyperlinkRegistry,
    ParseQualityReport,
    Stage2Output,
    TableRegistry,
)
from backend.modules.ingestion.contracts.stage_5_contracts import Stage5Output


class SectionType(str, Enum):
    """Locked 10-type section taxonomy used by Stage 6 classification."""

    OVERVIEW = "OVERVIEW"
    REQUIREMENTS = "REQUIREMENTS"
    ARCHITECTURE = "ARCHITECTURE"
    PROCESS_FLOW = "PROCESS_FLOW"
    DATA_MODEL = "DATA_MODEL"
    API_SPECIFICATION = "API_SPECIFICATION"
    INTEGRATION = "INTEGRATION"
    SECURITY = "SECURITY"
    TESTING = "TESTING"
    RISKS_ASSUMPTIONS_CONSTRAINTS = "RISKS_ASSUMPTIONS_CONSTRAINTS"


class StructuralSignals(BaseModel):
    """Deterministic structural signals detected within a section."""

    model_config = ConfigDict(extra="forbid")

    has_table: bool = False
    has_list: bool = False
    has_requirement_pattern: bool = False
    has_asset_reference: bool = False
    has_h3_subheading: bool = False
    estimated_tokens: int = Field(..., ge=0)


class SegmentedSection(BaseModel):
    """Represents a single segmented section produced by Stage 6."""

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(..., min_length=1)
    heading: str = Field(..., min_length=1)
    heading_level: int = Field(..., ge=0, le=2)
    section_index: int = Field(..., ge=1)
    section_type: SectionType
    raw_content: str = Field(..., min_length=1)
    preview_text: str = Field(..., min_length=1)
    structural_signals: StructuralSignals
    warnings: list[StageWarning] = Field(default_factory=list)


class Stage6Metrics(BaseModel):
    """Metrics emitted by Stage 6 for observability and debugging."""

    model_config = ConfigDict(extra="forbid")

    total_sections: int = Field(..., ge=0)
    heading_matched_sections: int = Field(..., ge=0)
    synthetic_sections: int = Field(..., ge=0)
    total_duration_ms: float = Field(..., ge=0)


class Stage6Input(BaseModel):
    """
    Input payload for Stage 6 segmentation.

    Preferred upstream source:
    - Stage 5 output (vision-enriched markdown)

    Backward-compatible source:
    - Stage 2 output (plain enriched markdown)

    The field name `enriched_markdown` is intentionally retained so the rest
    of the Stage 6/7/8 path does not need to be redesigned. After Stage 5,
    this field simply carries the latest pre-segmentation working markdown.
    """

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    source_blob: BlobArtifactReference
    enriched_markdown: str = Field(..., min_length=1)
    enriched_markdown_artifact: BlobArtifactReference
    asset_registry: AssetRegistry
    hyperlink_registry: HyperlinkRegistry
    table_registry: TableRegistry
    parse_quality_report: ParseQualityReport
    correlation_id: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    prior_warnings: list[StageWarning] = Field(default_factory=list)

    @classmethod
    def from_stage_2_output(cls, stage_2_output: Stage2Output) -> "Stage6Input":
        """Create a Stage 6 input contract from Stage 2 output."""
        return cls(
            process_id=stage_2_output.process_id,
            document_id=stage_2_output.document_id,
            source_blob=stage_2_output.source_blob,
            enriched_markdown=stage_2_output.enriched_markdown,
            enriched_markdown_artifact=stage_2_output.enriched_markdown_artifact,
            asset_registry=stage_2_output.asset_registry,
            hyperlink_registry=stage_2_output.hyperlink_registry,
            table_registry=stage_2_output.table_registry,
            parse_quality_report=stage_2_output.parse_quality_report,
            prior_warnings=stage_2_output.warnings,
        )

    @classmethod
    def from_stage_5_output(cls, stage_5_output: Stage5Output) -> "Stage6Input":
        """
        Create a Stage 6 input contract from Stage 5 output.

        This is the preferred final convergence path because Stage 5 may have
        injected [VISION_EXTRACTED: ...] blocks into the working markdown.
        """
        return cls(
            process_id=stage_5_output.process_id,
            document_id=stage_5_output.document_id,
            source_blob=stage_5_output.source_blob,
            enriched_markdown=stage_5_output.vision_enriched_markdown,
            enriched_markdown_artifact=stage_5_output.vision_enriched_markdown_artifact,
            asset_registry=stage_5_output.asset_registry,
            hyperlink_registry=stage_5_output.hyperlink_registry,
            table_registry=stage_5_output.table_registry,
            parse_quality_report=stage_5_output.parse_quality_report,
            prior_warnings=stage_5_output.warnings,
        )


class Stage6Output(BaseModel):
    """Output payload for Stage 6 segmentation."""

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    source_blob: BlobArtifactReference
    enriched_markdown_artifact: BlobArtifactReference
    sections: list[SegmentedSection] = Field(default_factory=list)
    warnings: list[StageWarning] = Field(default_factory=list)
    metrics: Stage6Metrics