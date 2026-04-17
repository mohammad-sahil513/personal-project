"""
Application DTOs for template metadata.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class TemplateDTO:
    template_id: str
    filename: str
    template_type: str | None
    version: str | None
    status: str
    created_at: str
    updated_at: str
    compile_job_id: str | None = None
    compiled_artifacts: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)