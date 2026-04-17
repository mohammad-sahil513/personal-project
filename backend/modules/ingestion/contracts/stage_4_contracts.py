"""
Stage 4 contracts for ingestion: image classification.

Stage 4 responsibilities:
- run a deterministic pre-filter first
- send only ambiguous image assets to the classifier path
- update the shared asset registry with image class labels
- preserve Stage 3 outputs required by later stages
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
    AssetRecord,
    AssetRegistry,
    HyperlinkRegistry,
    ParseQualityReport,
    TableRegistry,
)
from backend.modules.ingestion.contracts.stage_3_contracts import (
    MaskedCandidateRecord,
    Stage3Output,
)


class ClassificationSource(str, Enum):
    """How an image classification decision was produced."""

    DETERMINISTIC_PREFILTER = "DETERMINISTIC_PREFILTER"
    AMBIGUOUS_CLASSIFIER = "AMBIGUOUS_CLASSIFIER"
    SKIPPED_NON_IMAGE = "SKIPPED_NON_IMAGE"


class ImageClassificationDecision(BaseModel):
    """A single Stage 4 classification decision for an asset."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str = Field(..., min_length=1)
    classification: AssetClassification
    classification_source: ClassificationSource
    reason: str = Field(..., min_length=1)


class Stage4Metrics(BaseModel):
    """Metrics emitted by Stage 4 image classification."""

    model_config = ConfigDict(extra="forbid")

    total_assets_received: int = Field(..., ge=0)
    total_image_assets: int = Field(..., ge=0)
    deterministic_classification_count: int = Field(..., ge=0)
    ambiguous_classification_count: int = Field(..., ge=0)
    total_vision_eligible_assets: int = Field(..., ge=0)
    prefilter_duration_ms: float = Field(..., ge=0)
    classifier_duration_ms: float = Field(..., ge=0)
    persistence_duration_ms: float = Field(..., ge=0)
    total_duration_ms: float = Field(..., ge=0)


class Stage4Input(BaseModel):
    """
    Input payload for Stage 4 image classification.

    Stage 4 consumes the Stage 3 output so that masked markdown and all prior
    artifacts remain available for downstream stages.
    """

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    source_blob: BlobArtifactReference

    masked_markdown: str = Field(..., min_length=1)
    masked_markdown_artifact: BlobArtifactReference
    secure_mapping_artifact: BlobArtifactReference | None = None

    asset_registry: AssetRegistry
    hyperlink_registry: HyperlinkRegistry
    table_registry: TableRegistry
    parse_quality_report: ParseQualityReport

    handled_candidates: list[MaskedCandidateRecord] = Field(default_factory=list)
    correlation_id: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    prior_warnings: list[StageWarning] = Field(default_factory=list)

    @classmethod
    def from_stage_3_output(cls, stage_3_output: Stage3Output) -> "Stage4Input":
        """Create Stage 4 input from Stage 3 output."""
        return cls(
            process_id=stage_3_output.process_id,
            document_id=stage_3_output.document_id,
            source_blob=stage_3_output.source_blob,
            masked_markdown=stage_3_output.masked_markdown,
            masked_markdown_artifact=stage_3_output.masked_markdown_artifact,
            secure_mapping_artifact=stage_3_output.secure_mapping_artifact,
            asset_registry=stage_3_output.asset_registry,
            hyperlink_registry=stage_3_output.hyperlink_registry,
            table_registry=stage_3_output.table_registry,
            parse_quality_report=stage_3_output.parse_quality_report,
            handled_candidates=stage_3_output.handled_candidates,
            prior_warnings=stage_3_output.warnings,
        )


class Stage4Output(BaseModel):
    """Output payload for Stage 4 image classification."""

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
    decisions: list[ImageClassificationDecision] = Field(default_factory=list)
    warnings: list[StageWarning] = Field(default_factory=list)
    metrics: Stage4Metrics