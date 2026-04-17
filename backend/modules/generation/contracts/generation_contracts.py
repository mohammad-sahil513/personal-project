"""
Generation module runtime contracts.

This file defines the Generation-owned contract layer for:
- public strategy names
- section execution status / outcomes
- section output payloads
- job-level request / response models

Important:
- Do NOT redefine Template's ResolvedSection here.
- Do NOT add database/ORM assumptions here.
- Keep this file focused on Generation-owned runtime contracts only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class GenerationStrategy(str, Enum):
    """
    Public Generation strategy names.

    NOTE:
    - Keep `diagram_plantuml` as the only public diagram strategy name.
    - Do NOT introduce `diagram_mermaid` here.
    """

    SUMMARIZE_TEXT = "summarize_text"
    GENERATE_TABLE = "generate_table"
    DIAGRAM_PLANTUML = "diagram_plantuml"


class SectionExecutionStatus(str, Enum):
    """
    Lifecycle and terminal states for a section during Generation.
    """

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    GENERATED = "generated"
    DEGRADED = "degraded"
    SKIPPED = "skipped"
    FAILED = "failed"


class OutputType(str, Enum):
    """
    Supported section output payload categories.
    """

    MARKDOWN_TEXT = "markdown_text"
    MARKDOWN_TABLE = "markdown_table"
    DIAGRAM_ARTIFACT = "diagram_artifact"


class GenerationWarningCode(str, Enum):
    """
    Typed warnings for section-level Generation outcomes.
    """

    LOW_EVIDENCE = "low_evidence"
    PARTIAL_EVIDENCE = "partial_evidence"
    VALIDATION_RETRY_USED = "validation_retry_used"
    DIAGRAM_REPAIR_USED = "diagram_repair_used"
    STRATEGY_DEGRADED = "strategy_degraded"


class GenerationJobStatus(str, Enum):
    """
    Job-level lifecycle states for a Generation request.
    """

    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class DiagramArtifactRefs(BaseModel):
    """
    Artifact references produced by a diagram generation section.

    These are references/paths only; actual artifact creation happens later
    in the diagram runtime and artifact store services.
    """

    model_config = ConfigDict(extra="forbid")

    puml_path: str | None = Field(
        default=None,
        description="Canonical PlantUML source artifact path/reference.",
    )
    repaired_puml_paths: list[str] = Field(
        default_factory=list,
        description="Ordered references to repaired PlantUML source iterations.",
    )
    svg_path: str | None = Field(
        default=None,
        description="Rendered SVG artifact path/reference.",
    )
    png_path: str | None = Field(
        default=None,
        description="Rendered PNG artifact path/reference.",
    )
    manifest_path: str | None = Field(
        default=None,
        description="Diagram artifact manifest path/reference.",
    )


class SectionOutput(BaseModel):
    """
    Structured output payload for a single generated section.

    Rules:
    - MARKDOWN_TEXT requires `content_markdown`
    - MARKDOWN_TABLE requires `content_markdown`
    - DIAGRAM_ARTIFACT requires `diagram_artifacts`
    """

    model_config = ConfigDict(extra="forbid")

    output_type: OutputType = Field(
        description="High-level category of the produced section output."
    )
    content_markdown: str | None = Field(
        default=None,
        description="Markdown content for text/table outputs.",
    )
    diagram_artifacts: DiagramArtifactRefs | None = Field(
        default=None,
        description="Diagram artifact references for diagram outputs.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional Generation-owned metadata for downstream assembly/export.",
    )

    @model_validator(mode="after")
    def validate_output_payload(self) -> "SectionOutput":
        """
        Ensure the payload matches the selected output type.
        """
        if self.output_type in {OutputType.MARKDOWN_TEXT, OutputType.MARKDOWN_TABLE}:
            if not self.content_markdown or not self.content_markdown.strip():
                raise ValueError(
                    "content_markdown is required for markdown_text and markdown_table outputs."
                )
            if self.diagram_artifacts is not None:
                raise ValueError(
                    "diagram_artifacts must be omitted for markdown_text and markdown_table outputs."
                )

        if self.output_type == OutputType.DIAGRAM_ARTIFACT:
            if self.diagram_artifacts is None:
                raise ValueError(
                    "diagram_artifacts is required for diagram_artifact outputs."
                )

        return self


class SectionGenerationResult(BaseModel):
    """
    Final result of one section execution.

    This model is used by:
    - section executor
    - session state
    - assembly/export
    - API/status surfaces
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="Stable section identifier from upstream planning.")
    section_heading: str | None = Field(
        default=None,
        description="Human-readable section heading/title.",
    )
    strategy: GenerationStrategy = Field(
        description="Resolved Generation strategy used for this section."
    )
    status: SectionExecutionStatus = Field(
        description="Current or terminal execution status of the section."
    )
    output: SectionOutput | None = Field(
        default=None,
        description="Generated output payload, if available.",
    )
    warnings: list[GenerationWarningCode] = Field(
        default_factory=list,
        description="Typed section-level warnings.",
    )
    low_evidence: bool = Field(
        default=False,
        description="True when the section was generated with insufficient SOURCE evidence.",
    )
    manual_review_required: bool = Field(
        default=False,
        description="True when the section requires downstream manual review.",
    )
    error_message: str | None = Field(
        default=None,
        description="Terminal failure detail when status=failed.",
    )
    started_at: datetime | None = Field(
        default=None,
        description="Section execution start timestamp (UTC).",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Section execution completion timestamp (UTC).",
    )

    @model_validator(mode="after")
    def validate_result_state(self) -> "SectionGenerationResult":
        """
        Enforce basic consistency rules for section results.
        """
        terminal_statuses = {
            SectionExecutionStatus.GENERATED,
            SectionExecutionStatus.DEGRADED,
            SectionExecutionStatus.SKIPPED,
            SectionExecutionStatus.FAILED,
        }

        # Failed sections should provide an error message.
        if self.status == SectionExecutionStatus.FAILED and not self.error_message:
            raise ValueError("error_message is required when status=failed.")

        # Generated/degraded sections normally carry output.
        if self.status in {SectionExecutionStatus.GENERATED, SectionExecutionStatus.DEGRADED}:
            if self.output is None:
                raise ValueError(
                    "output is required when status is generated or degraded."
                )

        # Low-evidence sections should require manual review.
        if self.low_evidence and not self.manual_review_required:
            raise ValueError(
                "manual_review_required must be True when low_evidence is True."
            )

        # completed_at should be set only for terminal states.
        if self.completed_at is not None and self.status not in terminal_statuses:
            raise ValueError(
                "completed_at can only be set for terminal section statuses."
            )

        return self


class GenerationRequestOptions(BaseModel):
    """
    Optional execution/export flags for a Generation job request.
    """

    model_config = ConfigDict(extra="forbid")

    emit_sse: bool = Field(
        default=True,
        description="Whether live progress events should be emitted.",
    )
    export_pdf: bool = Field(
        default=False,
        description="Whether PDF export should be attempted after DOCX export.",
    )
    allow_markdown_fallback: bool = Field(
        default=True,
        description="Whether Markdown fallback is allowed if DOCX/PDF export fail.",
    )


class GenerationJobRequest(BaseModel):
    """
    API-facing request model for starting a Generation job.

    NOTE:
    - This request intentionally carries document/template/job metadata only.
    - Template's `ResolvedSection` list is consumed internally by Generation
      after upstream template resolution; it is not redefined here.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(description="Stable Generation job identifier.")
    document_id: str = Field(description="Target source/document identifier.")
    template_id: str = Field(description="Template identifier selected for the job.")
    template_version: str | None = Field(
        default=None,
        description="Optional template version identifier.",
    )
    options: GenerationRequestOptions = Field(
        default_factory=GenerationRequestOptions,
        description="Execution and export options for the job.",
    )


class GenerationJobSummary(BaseModel):
    """
    Job-level summary counts used in status and completion responses.
    """

    model_config = ConfigDict(extra="forbid")

    total_sections: int = Field(default=0, ge=0)
    pending_sections: int = Field(default=0, ge=0)
    running_sections: int = Field(default=0, ge=0)
    generated_sections: int = Field(default=0, ge=0)
    degraded_sections: int = Field(default=0, ge=0)
    skipped_sections: int = Field(default=0, ge=0)
    failed_sections: int = Field(default=0, ge=0)


class GenerationJobResponse(BaseModel):
    """
    Job-level response/status contract returned by Generation orchestration.

    Export details are intentionally left as a generic mapping for now to avoid
    cross-module import cycles during Phase 1. A typed export contract will be
    introduced in `export_contracts.py`.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(description="Stable Generation job identifier.")
    document_id: str = Field(description="Target source/document identifier.")
    template_id: str = Field(description="Template identifier used for the job.")
    template_version: str | None = Field(
        default=None,
        description="Optional template version identifier.",
    )
    status: GenerationJobStatus = Field(
        description="Current or terminal job-level status."
    )
    summary: GenerationJobSummary = Field(
        default_factory=GenerationJobSummary,
        description="Aggregated section execution counts.",
    )
    section_results: list[SectionGenerationResult] = Field(
        default_factory=list,
        description="Per-section execution results accumulated for the job.",
    )
    export_summary: dict[str, Any] | None = Field(
        default=None,
        description="Placeholder for typed export summary contract introduced later.",
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="Job creation timestamp (UTC).",
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        description="Last job update timestamp (UTC).",
    )