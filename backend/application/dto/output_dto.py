"""
Application DTOs for workflow outputs.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class OutputDTO:
    output_id: str
    workflow_run_id: str
    status: str
    output_type: str
    format: str
    created_at: str
    updated_at: str
    artifact_path: str | None = None
    metadata: dict[str, Any] | None = None
    errors: list[dict[str, Any]] | None = None

    def to_dict(self) -> dict:
        return asdict(self)