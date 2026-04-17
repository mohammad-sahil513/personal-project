"""
Application DTOs for ingestion execution metadata.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class IngestionExecutionDTO:
    execution_id: str
    workflow_run_id: str
    document_id: str
    type: str
    status: str
    current_stage: str
    completed_stages: int
    total_stages: int
    created_at: str
    updated_at: str
    warnings: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)