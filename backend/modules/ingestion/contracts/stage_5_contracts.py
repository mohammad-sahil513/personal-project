"""
Stage 5 contracts for ingestion: selective vision extraction.

Stage 5 responsibilities:
- process only vision-eligible image assets
- enforce priority order: flowchart > architecture > sequence > generic diagram
- enforce a hard cap on vision extraction calls per document
- validate extracted JSON
- inject [VISION_EXTRACTED: ...] blocks into markdown
- persist the enriched markdown and extraction manifest
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
    AssetClassification,
    AssetRegistry,
    HyperlinkRegistry,
    ParseQualityReport,
    TableRegistry,
)
from backend.modules.ingestion.contracts.stage_3_contracts import MaskedCandidateRecord
from backend.modules.ingestion.contracts.stage_4_contracts import Stage4Output


class VisionExtractionStatus(str, Enum):
    """Outcome status for a single Stage 5 vision-eligible asset."""

    EXTRACTED = "EXTRACTED"
    SKIPPED_NOT_ELIGIBLE = "SKIPPED_NOT_ELIGIBLE"
    SKIPPED_CALL_CAP = "SKIPPED_CALL_CAP"
    FAILED = "FAILED"


class VisionExtractionRecord(BaseModel):
    """Result record for one asset considered during Stage 5."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(..., min_length=1)
    classification: AssetClassification
    status: VisionExtractionStatus
    priority_rank: int | None = Field(default=None, ge=1)
    extraction_payload: dict[str, Any] | None = None
    extraction_summary: str | None = None
    injected_block: str | None = None
    reason: str = Field(..., min_length=1)


class Stage5Metrics(BaseModel):
    """Metrics emitted by Stage 5 selective vision extraction."""

    model_config = ConfigDict(extra="forbid")

    total_assets_received: int = Field(..., ge=0)
    total_vision_eligible_assets: int = Field(..., ge=0)
    total_vision_calls_attempted: int = Field(..., ge=0)
    total_extractions_completed: int = Field(..., ge=0)
    total_skipped_by_cap: int = Field(..., ge=0)
    total_failures: int = Field(..., ge=0)
    extraction_duration_ms: float = Field(..., ge=0)
    persistence_duration_ms: float = Field(..., ge=0)
    total_duration_ms: float = Field(..., ge=0)


class Stage5Input(BaseModel):
    """
    Input payload for Stage 5 vision extraction.

    Stage 5 consumes Stage 4 output so that:
    - masked markdown remains the working markdown base
    - the asset registry already contains image classifications
    """

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    source_blob: BlobArtifactReference

    masked_markdown: str = Field(..., min_length=1)
    masked_markdown_artifact: BlobArtifactReference
    secure_mapping_artifact: BlobArtifactReference | None = None

    asset_registry: AssetRegistry
    classified_asset_registry_artifact: BlobArtifactReference
    hyperlink_registry: HyperlinkRegistry
    table_registry: TableRegistry
    parse_quality_report: ParseQualityReport

    handled_candidates: list[MaskedCandidateRecord] = Field(default_factory=list)
    max_vision_calls: int = Field(default=10, ge=1, le=100)
    correlation_id: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    prior_warnings: list[StageWarning] = Field(default_factory=list)

    @classmethod
    def from_stage_4_output(
        cls,
        stage_4_output: Stage4Output,
        *,
        max_vision_calls: int = 10,
    ) -> "Stage5Input":
        """Create Stage 5 input from Stage 4 output."""
        return cls(
            process_id=stage_4_output.process_id,
            document_id=stage_4_output.document_id,
            source_blob=stage_4_output.source_blob,
            masked_markdown=stage_4_output.masked_markdown,
            masked_markdown_artifact=stage_4_output.masked_markdown_artifact,
            secure_mapping_artifact=stage_4_output.secure_mapping_artifact,
            asset_registry=stage_4_output.asset_registry,
            classified_asset_registry_artifact=stage_4_output.classified_asset_registry_artifact,
            hyperlink_registry=stage_4_output.hyperlink_registry,
            table_registry=stage_4_output.table_registry,
            parse_quality_report=stage_4_output.parse_quality_report,
            handled_candidates=stage_4_output.handled_candidates,
            max_vision_calls=max_vision_calls,
            prior_warnings=stage_4_output.warnings,
        )


class Stage5Output(BaseModel):
    """Output payload for Stage 5 selective vision extraction."""

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    source_blob: BlobArtifactReference

    vision_enriched_markdown: str = Field(..., min_length=1)
    vision_enriched_markdown_artifact: BlobArtifactReference
    extraction_manifest_artifact: BlobArtifactReference

    asset_registry: AssetRegistry
    hyperlink_registry: HyperlinkRegistry
    table_registry: TableRegistry
    parse_quality_report: ParseQualityReport
    handled_candidates: list[MaskedCandidateRecord] = Field(default_factory=list)

    extraction_records: list[VisionExtractionRecord] = Field(default_factory=list)
    warnings: list[StageWarning] = Field(default_factory=list)
    metrics: Stage5Metrics