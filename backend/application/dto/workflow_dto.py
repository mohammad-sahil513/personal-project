"""
Application DTOs for workflow metadata.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class WorkflowDTO:
    workflow_run_id: str
    status: str
    current_phase: str
    overall_progress_percent: int
    document_id: str
    template_id: str | None
    output_id: str | None
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    phases: list[dict[str, Any]] | None = None
    execution_refs: dict[str, str] | None = None

    section_plan: dict[str, Any] | None = None
    section_progress: dict[str, Any] | None = None
    section_retrieval_results: dict[str, Any] | None = None
    section_generation_results: dict[str, Any] | None = None
    assembled_document: dict[str, Any] | None = None
    observability_summary: dict[str, Any] | None = None

    warnings: list[dict[str, Any]] | None = None
    errors: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict:
        return asdict(self)