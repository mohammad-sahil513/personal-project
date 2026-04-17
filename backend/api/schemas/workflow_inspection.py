from pydantic import BaseModel
from typing import Any


class WorkflowErrorsResponse(BaseModel):
    workflow_run_id: str
    status: str
    errors: list[dict]


class WorkflowArtifactsResponse(BaseModel):
    workflow_run_id: str
    artifacts: list[dict]


class WorkflowEventsResponse(BaseModel):
    workflow_run_id: str
    events: list[dict]


class WorkflowDiagnosticsResponse(BaseModel):
    workflow_run_id: str
    status: str
    current_phase: str
    overall_progress_percent: int
    has_errors: bool
    has_output: bool
    sections: dict[str, int]