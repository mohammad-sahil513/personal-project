from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LogMode(str, Enum):
    OFFICIAL = "official"
    DEMO = "demo"
    BOTH = "both"


class RunPaths(BaseModel):
    """Resolved filesystem paths for one ingestion run."""

    model_config = ConfigDict(extra="forbid")

    root_dir: Path
    logs_dir: Path
    artifacts_dir: Path
    official_log_path: Path
    demo_log_path: Path


class IngestionRunContext(BaseModel):
    """Metadata describing one ingestion execution."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(..., min_length=1)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    file_name: str = Field(..., min_length=1)
    content_type: str = Field(..., min_length=1)
    file_size_bytes: int = Field(..., ge=1)
    log_mode: LogMode
    paths: RunPaths


class StageUsageSummary(BaseModel):
    """
    Usage-style metrics for one stage.

    This is intentionally *not* billing-grade cost. It is a compact summary
    of the measurable work the stage performed so demo viewers can understand
    what each step consumed.
    """

    model_config = ConfigDict(extra="forbid")

    metrics: dict[str, Any] = Field(default_factory=dict)


class StageObservation(BaseModel):
    """Observation record for one stage run."""

    model_config = ConfigDict(extra="forbid")

    stage_name: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)
    started_at: datetime
    completed_at: datetime | None = None
    duration_ms: float | None = Field(default=None, ge=0)
    safe_metadata: dict[str, Any] = Field(default_factory=dict)
    usage_summary: StageUsageSummary = Field(default_factory=StageUsageSummary)
    warning_count: int = Field(default=0, ge=0)
    error_message: str | None = None