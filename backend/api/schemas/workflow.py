"""
API schema models for workflow routes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowCreateRequest(BaseModel):
    document_id: str
    template_id: str | None = None
    start_immediately: bool = True


class WorkflowPhaseState(BaseModel):
    phase: str
    status: str
    progress_percent: int
    weight: int


class IngestionStatusResponseData(BaseModel):
    execution_id: str
    status: str
    current_stage: str
    current_stage_label: str
    completed_stages: int
    total_stages: int
    progress_percent: int
    warnings_count: int
    errors_count: int
    artifact_count: int
    has_duplicate_warning: bool
    has_validation_error: bool
    terminal_hint: str | None = None
    warnings: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    artifacts: list[dict] = Field(default_factory=list)


class WorkflowSectionPlanItem(BaseModel):
    section_id: str
    title: str
    execution_order: int
    generation_strategy: str
    retrieval_profile: str
    dependencies: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class WorkflowSectionProgressItem(BaseModel):
    section_id: str
    title: str
    execution_order: int
    generation_strategy: str
    retrieval_profile: str
    status: str
    progress_percent: int
    dependencies: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class WorkflowSectionProgressSummary(BaseModel):
    total_sections: int
    completed_sections: int
    running_sections: int
    failed_sections: int
    sections: list[WorkflowSectionProgressItem] = Field(default_factory=list)


class WorkflowSectionPlanResponseData(BaseModel):
    workflow_run_id: str
    template_id: str
    total_sections: int
    sections: list[WorkflowSectionPlanItem]


class WorkflowSummaryResponseData(BaseModel):
    workflow_run_id: str
    status: str
    current_phase: str
    overall_progress_percent: int
    document_id: str
    template_id: str | None = None
    output_id: str | None = None
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    phases: list[WorkflowPhaseState] = Field(default_factory=list)
    execution_refs: dict[str, str] = Field(default_factory=dict)
    section_plan: dict | None = None
    section_progress: dict | None = None
    warnings: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)


class WorkflowCreateResponseData(WorkflowSummaryResponseData):
    dispatch_mode: str | None = None


class WorkflowListResponseData(BaseModel):
    items: list[WorkflowSummaryResponseData]
    total: int


class WorkflowStatusResponseData(WorkflowSummaryResponseData):
    current_step_label: str | None = None
    ingestion: IngestionStatusResponseData | None = None