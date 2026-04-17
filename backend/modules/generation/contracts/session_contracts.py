"""
Generation module session/runtime contracts.

This file defines:
- per-section runtime state
- wave execution state
- snapshot metadata
- full Generation session state

Important:
- Keep this file focused on runtime/session contracts only.
- Do NOT introduce database/ORM assumptions.
- Snapshot references are file/blob artifact references, not DB rows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.modules.generation.contracts.generation_contracts import (
    DiagramArtifactRefs,
    GenerationJobStatus,
    GenerationStrategy,
    SectionExecutionStatus,
    SectionGenerationResult,
)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class SnapshotScope(str, Enum):
    """
    Snapshot granularity used for file/blob-backed session persistence.
    """

    SECTION = "section"
    WAVE = "wave"
    JOB = "job"


class SectionDependencyState(str, Enum):
    """
    Dependency readiness state for a section.
    """

    UNBLOCKED = "unblocked"
    BLOCKED = "blocked"
    SATISFIED = "satisfied"


class SnapshotMetadata(BaseModel):
    """
    Metadata describing one persisted snapshot artifact.
    """

    model_config = ConfigDict(extra="forbid")

    snapshot_id: str = Field(description="Stable snapshot identifier.")
    scope: SnapshotScope = Field(
        description="Granularity of the snapshot (section/wave/job)."
    )
    path: str = Field(
        description="File/blob artifact path/reference for the snapshot."
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="Snapshot creation timestamp (UTC).",
    )
    revision: int = Field(
        default=1,
        ge=1,
        description="Monotonic snapshot revision number.",
    )
    related_section_id: str | None = Field(
        default=None,
        description="Section identifier if the snapshot is section-scoped.",
    )
    related_wave_index: int | None = Field(
        default=None,
        ge=0,
        description="Wave index if the snapshot is wave-scoped.",
    )

    @model_validator(mode="after")
    def validate_scope_relationship(self) -> "SnapshotMetadata":
        """
        Ensure scope-specific linkage fields are used consistently.
        """
        if self.scope == SnapshotScope.SECTION and not self.related_section_id:
            raise ValueError(
                "related_section_id is required when scope='section'."
            )

        if self.scope == SnapshotScope.WAVE and self.related_wave_index is None:
            raise ValueError(
                "related_wave_index is required when scope='wave'."
            )

        return self


class WaveExecutionState(BaseModel):
    """
    Runtime status for one dependency execution wave.

    This is a contract placeholder for the wave-based execution optimization
    layered on top of the approved dependency-aware Generation design.
    """

    model_config = ConfigDict(extra="forbid")

    wave_index: int = Field(ge=0, description="Zero-based wave number.")
    ready_section_ids: list[str] = Field(
        default_factory=list,
        description="Sections released for execution in this wave.",
    )
    running_section_ids: list[str] = Field(
        default_factory=list,
        description="Sections currently executing in this wave.",
    )
    completed_section_ids: list[str] = Field(
        default_factory=list,
        description="Sections that reached terminal status in this wave.",
    )
    failed_section_ids: list[str] = Field(
        default_factory=list,
        description="Sections that failed within this wave.",
    )
    started_at: datetime | None = Field(
        default=None,
        description="Wave start timestamp (UTC).",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Wave completion timestamp (UTC).",
    )

    @model_validator(mode="after")
    def validate_wave_lists(self) -> "WaveExecutionState":
        """
        Ensure section IDs are not duplicated across the same wave-state buckets.
        """
        all_ids = (
            self.ready_section_ids
            + self.running_section_ids
            + self.completed_section_ids
            + self.failed_section_ids
        )
        if len(all_ids) != len(set(all_ids)):
            raise ValueError(
                "A section_id cannot appear in multiple wave-state buckets simultaneously."
            )

        return self


class SectionRuntimeState(BaseModel):
    """
    Runtime execution state for one resolved section.

    This model tracks:
    - section-level lifecycle state
    - dependency information
    - retrieval linkage placeholders
    - final SectionGenerationResult, once available
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="Stable section identifier.")
    section_heading: str | None = Field(
        default=None,
        description="Human-readable section heading/title.",
    )
    strategy: GenerationStrategy = Field(
        description="Resolved Generation strategy for this section."
    )
    status: SectionExecutionStatus = Field(
        default=SectionExecutionStatus.PENDING,
        description="Current lifecycle state of the section.",
    )
    dependency_state: SectionDependencyState = Field(
        default=SectionDependencyState.BLOCKED,
        description="Current dependency readiness state for the section.",
    )
    dependency_ids: list[str] = Field(
        default_factory=list,
        description="Upstream section identifiers that this section depends on.",
    )
    retrieval_id: str | None = Field(
        default=None,
        description="Optional retrieval operation identifier for this section.",
    )
    assigned_wave_index: int | None = Field(
        default=None,
        ge=0,
        description="Wave index assigned for execution, if planned.",
    )
    started_at: datetime | None = Field(
        default=None,
        description="Section execution start timestamp (UTC).",
    )
    completed_at: datetime | None = Field(
        default=None,
        description="Section execution completion timestamp (UTC).",
    )
    result: SectionGenerationResult | None = Field(
        default=None,
        description="Final structured section result, once available.",
    )

    @model_validator(mode="after")
    def validate_runtime_state(self) -> "SectionRuntimeState":
        """
        Enforce consistency between runtime state and final result.
        """
        terminal_statuses = {
            SectionExecutionStatus.GENERATED,
            SectionExecutionStatus.DEGRADED,
            SectionExecutionStatus.SKIPPED,
            SectionExecutionStatus.FAILED,
        }

        # completed_at should exist only for terminal statuses
        if self.completed_at is not None and self.status not in terminal_statuses:
            raise ValueError(
                "completed_at can only be set for terminal section statuses."
            )

        # Terminal sections should have a result model.
        if self.status in terminal_statuses and self.result is None:
            raise ValueError(
                "result is required when section status is terminal."
            )

        # If result exists, it must match the owning section/strategy/status.
        if self.result is not None:
            if self.result.section_id != self.section_id:
                raise ValueError("result.section_id must match section_id.")
            if self.result.strategy != self.strategy:
                raise ValueError("result.strategy must match strategy.")
            if self.result.status != self.status:
                raise ValueError("result.status must match runtime status.")

        return self


class GenerationSessionState(BaseModel):
    """
    In-memory runtime state for a Generation job.

    The approved Generation plan explicitly requires:
    - in-memory runtime state during execution
    - snapshot persistence after each section
    - no DB assumptions for this phase
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(description="Stable Generation job identifier.")
    document_id: str = Field(description="Target source/document identifier.")
    template_id: str = Field(description="Template identifier selected for the job.")
    template_version: str | None = Field(
        default=None,
        description="Optional template version identifier.",
    )
    job_status: GenerationJobStatus = Field(
        default=GenerationJobStatus.ACCEPTED,
        description="Current job-level lifecycle state.",
    )
    current_wave_index: int | None = Field(
        default=None,
        ge=0,
        description="Currently active execution wave index, if any.",
    )
    section_states: dict[str, SectionRuntimeState] = Field(
        default_factory=dict,
        description="Map of section_id -> runtime state.",
    )
    wave_states: list[WaveExecutionState] = Field(
        default_factory=list,
        description="Execution wave runtime metadata.",
    )
    diagram_artifact_index: dict[str, DiagramArtifactRefs] = Field(
        default_factory=dict,
        description="Optional quick-lookup map for diagram artifacts by section_id.",
    )
    export_summary: dict[str, Any] | None = Field(
        default=None,
        description="Placeholder for typed export summary contract.",
    )
    snapshots: list[SnapshotMetadata] = Field(
        default_factory=list,
        description="Snapshot history for file/blob-backed persistence.",
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        description="Session creation timestamp (UTC).",
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        description="Session last-update timestamp (UTC).",
    )

    @model_validator(mode="after")
    def validate_session_state(self) -> "GenerationSessionState":
        """
        Validate top-level session consistency.
        """
        # Section-state map keys must match embedded section_ids.
        for section_id, state in self.section_states.items():
            if state.section_id != section_id:
                raise ValueError(
                    f"section_states key '{section_id}' does not match embedded section_id '{state.section_id}'."
                )

        # Diagram artifact index keys must reference known sections.
        for section_id in self.diagram_artifact_index:
            if section_id not in self.section_states:
                raise ValueError(
                    f"diagram_artifact_index contains unknown section_id '{section_id}'."
                )

        # current_wave_index must reference an existing wave if present.
        if self.current_wave_index is not None:
            available_indices = {wave.wave_index for wave in self.wave_states}
            if self.current_wave_index not in available_indices:
                raise ValueError(
                    "current_wave_index must reference a wave present in wave_states."
                )

        return self