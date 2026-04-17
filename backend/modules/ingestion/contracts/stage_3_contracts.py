"""
Stage 3 contracts for ingestion: PII detection and selective masking.

Stage 3 responsibilities:
- detect candidate PII entities
- classify each candidate as MASK or KEEP
- selectively mask only confirmed PII
- persist the reversible mapping to secure blob storage
- keep only the secure mapping blob path in pipeline DTOs
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


class PiiEntityType(str, Enum):
    """Supported Stage 3 PII candidate entity types."""

    EMAIL_ADDRESS = "EMAIL_ADDRESS"
    PHONE_NUMBER = "PHONE_NUMBER"
    PERSON_NAME = "PERSON_NAME"


class PiiDecisionAction(str, Enum):
    """Allowed Stage 3 contextual classification decisions."""

    MASK = "MASK"
    KEEP = "KEEP"


class PiiCandidate(BaseModel):
    """
    Internal candidate representation used inside Stage 3.

    Important:
    - this includes the original matched value because masking logic needs it,
      but later pipeline outputs should never expose the reversible mapping inline.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(..., min_length=1)
    entity_type: PiiEntityType
    matched_text: str = Field(..., min_length=1)
    start_char: int = Field(..., ge=0)
    end_char: int = Field(..., gt=0)


class ContextualPiiDecision(BaseModel):
    """Decision emitted by the Stage 3 contextual classifier."""

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(..., min_length=1)
    entity_type: PiiEntityType
    action: PiiDecisionAction
    reason: str = Field(..., min_length=1)


class MaskedCandidateRecord(BaseModel):
    """
    Non-sensitive record describing how a candidate was handled.

    This model intentionally avoids carrying the original matched value.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(..., min_length=1)
    entity_type: PiiEntityType
    action: PiiDecisionAction
    placeholder: str | None = None
    reason: str = Field(..., min_length=1)


class Stage3Metrics(BaseModel):
    """Metrics emitted by Stage 3 PII processing."""

    model_config = ConfigDict(extra="forbid")

    total_candidates_detected: int = Field(..., ge=0)
    total_candidates_masked: int = Field(..., ge=0)
    total_candidates_kept: int = Field(..., ge=0)
    detection_duration_ms: float = Field(..., ge=0)
    classification_duration_ms: float = Field(..., ge=0)
    masking_duration_ms: float = Field(..., ge=0)
    persistence_duration_ms: float = Field(..., ge=0)
    total_duration_ms: float = Field(..., ge=0)


class Stage3Input(BaseModel):
    """
    Input payload for Stage 3 PII processing.

    Stage 3 consumes the Stage 2 enriched markdown and carries forward the
    enrichment registries and parse-quality report for downstream stages.
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

    pii_enabled: bool = True
    system_email_allowlist: list[str] = Field(default_factory=list)
    correlation_id: str | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    prior_warnings: list[StageWarning] = Field(default_factory=list)

    @classmethod
    def from_stage_2_output(
        cls,
        stage_2_output: Stage2Output,
        *,
        pii_enabled: bool = True,
        system_email_allowlist: list[str] | None = None,
    ) -> "Stage3Input":
        """Create Stage 3 input from Stage 2 output."""
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
            pii_enabled=pii_enabled,
            system_email_allowlist=system_email_allowlist or [],
            prior_warnings=stage_2_output.warnings,
        )


class Stage3Output(BaseModel):
    """
    Output payload for Stage 3 selective masking.

    Important:
    - pipeline output carries only the secure mapping blob artifact reference,
      not the reversible mapping content itself.
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
    warnings: list[StageWarning] = Field(default_factory=list)
    metrics: Stage3Metrics
   
class PiiClassifierCandidateContext(BaseModel):
    """
    Structured context payload sent to the Stage 3 classifier adapter.

    This model is internal to the classifier path and is used to generate a
    stable JSON payload for prompt-based classification.
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str = Field(..., min_length=1)
    entity_type: PiiEntityType
    matched_text: str = Field(..., min_length=1)
    surrounding_text: str = Field(..., min_length=1)
    is_allowlisted_system_value: bool = False


class PiiClassificationBatchRequest(BaseModel):
    """
    Batch request sent to the prompt-based Stage 3 classifier adapter.

    The deployment name defaults to `gpt5mini` because the locked ingestion
    plan explicitly uses GPT-5 Mini for Stage 3 contextual classification.
    """

    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(..., min_length=1)
    prompt_version: str = Field(default="pii_classification_v1", min_length=1)
    deployment_name: str = Field(default="gpt5mini", min_length=1)
    candidates: list[PiiClassifierCandidateContext] = Field(default_factory=list)


class PiiClassificationBatchResponse(BaseModel):
    """
    Parsed response from the prompt-based Stage 3 classifier adapter.

    This remains internal to Stage 3 and is used only to validate that the
    model output can be safely converted into ContextualPiiDecision objects.
    """

    model_config = ConfigDict(extra="forbid")

    deployment_name: str = Field(..., min_length=1)
    decisions: list[ContextualPiiDecision] = Field(default_factory=list)