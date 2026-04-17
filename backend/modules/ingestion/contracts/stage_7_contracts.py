"""
Stage 7 contracts for ingestion: validation.

Stage 7 responsibilities:
- validate parse quality
- validate section integrity
- validate asset and vision consistency
- validate PII masking / leak behavior
- validate pre-chunking readiness

The output of this stage must distinguish:
- global failures (pipeline should stop before chunking/indexing)
- localized warnings (pipeline may continue with warnings)
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
    ParseQualityReport,
)
from backend.modules.ingestion.contracts.stage_6_contracts import (
    SegmentedSection,
    Stage6Output,
)


class ValidationSeverity(str, Enum):
    """Severity levels for validation issues."""

    WARNING = "WARNING"
    ERROR = "ERROR"


class ValidationIssueCode(str, Enum):
    """Locked validation issue and warning codes for Stage 7."""

    EMPTY_MARKDOWN = "EMPTY_MARKDOWN"
    MISSING_HEADINGS = "MISSING_HEADINGS"
    TOKEN_SANITY_OUT_OF_BOUNDS = "TOKEN_SANITY_OUT_OF_BOUNDS"

    NO_SECTIONS_FOUND = "NO_SECTIONS_FOUND"
    DUPLICATE_SECTION_ID = "DUPLICATE_SECTION_ID"
    EMPTY_SECTION_CONTENT = "EMPTY_SECTION_CONTENT"
    INVALID_SECTION_TYPE = "INVALID_SECTION_TYPE"

    UNRESOLVED_ASSET_PLACEHOLDER = "UNRESOLVED_ASSET_PLACEHOLDER"
    UNREFERENCED_ASSET_REGISTRY_ENTRY = "UNREFERENCED_ASSET_REGISTRY_ENTRY"
    EMPTY_VISION_BLOCK = "EMPTY_VISION_BLOCK"

    POSSIBLE_PII_LEAK = "POSSIBLE_PII_LEAK"
    POSSIBLE_PII_LEAK_EXCLUDING_SYSTEM_IDENTIFIER = (
        "POSSIBLE_PII_LEAK_EXCLUDING_SYSTEM_IDENTIFIER"
    )

    OVERSIZED_SECTION_WARNING = "OVERSIZED_SECTION_WARNING"


class ValidationIssue(BaseModel):
    """Represents a single validation issue discovered during Stage 7."""

    model_config = ConfigDict(extra="forbid")

    severity: ValidationSeverity
    code: ValidationIssueCode
    message: str = Field(..., min_length=1)
    section_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationSummary(BaseModel):
    """Aggregated summary of all Stage 7 validation issues."""

    model_config = ConfigDict(extra="forbid")

    total_issues: int = Field(..., ge=0)
    error_count: int = Field(..., ge=0)
    warning_count: int = Field(..., ge=0)
    has_global_failure: bool = False
    can_proceed_to_chunking: bool = True


class Stage7Metrics(BaseModel):
    """Metrics emitted by Stage 7 validation."""

    model_config = ConfigDict(extra="forbid")

    total_sections_checked: int = Field(..., ge=0)
    total_assets_checked: int = Field(..., ge=0)
    total_duration_ms: float = Field(..., ge=0)


class Stage7Input(BaseModel):
    """
    Input payload for Stage 7 validation.

    Note:
    - Stage 6 output does not carry parse-quality and asset-registry data directly.
    - So Stage 7 accepts Stage 6 output plus the additional Stage 2 artifacts
      needed for validation.
    """

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    source_blob: BlobArtifactReference
    sections: list[SegmentedSection] = Field(default_factory=list)
    parse_quality_report: ParseQualityReport
    asset_registry: AssetRegistry
    enriched_markdown_artifact: BlobArtifactReference

    pii_enabled: bool = False
    pii_mapping_blob_path: str | None = None
    mapped_pii_values: list[str] = Field(default_factory=list)
    allowlisted_system_emails: list[str] = Field(default_factory=list)

    prior_warnings: list[StageWarning] = Field(default_factory=list)

    @classmethod
    def from_stage_6_output(
        cls,
        stage_6_output: Stage6Output,
        *,
        parse_quality_report: ParseQualityReport,
        asset_registry: AssetRegistry,
        pii_enabled: bool = False,
        pii_mapping_blob_path: str | None = None,
        mapped_pii_values: list[str] | None = None,
        allowlisted_system_emails: list[str] | None = None,
    ) -> "Stage7Input":
        """Create Stage 7 input from Stage 6 output plus Stage 2 validation artifacts."""
        return cls(
            process_id=stage_6_output.process_id,
            document_id=stage_6_output.document_id,
            source_blob=stage_6_output.source_blob,
            sections=stage_6_output.sections,
            parse_quality_report=parse_quality_report,
            asset_registry=asset_registry,
            enriched_markdown_artifact=stage_6_output.enriched_markdown_artifact,
            pii_enabled=pii_enabled,
            pii_mapping_blob_path=pii_mapping_blob_path,
            mapped_pii_values=mapped_pii_values or [],
            allowlisted_system_emails=allowlisted_system_emails or [],
            prior_warnings=stage_6_output.warnings,
        )


class Stage7Output(BaseModel):
    """Output payload for Stage 7 validation."""

    model_config = ConfigDict(extra="forbid")

    process_id: str = Field(..., min_length=1)
    document_id: str = Field(..., min_length=1)
    source_blob: BlobArtifactReference
    sections: list[SegmentedSection] = Field(default_factory=list)

    issues: list[ValidationIssue] = Field(default_factory=list)
    summary: ValidationSummary
    warnings: list[StageWarning] = Field(default_factory=list)
    metrics: Stage7Metrics