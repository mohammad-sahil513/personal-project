"""
Application DTOs for section-level generation results.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class GenerationResultDTO:
    section_id: str
    generation_strategy: str
    status: str
    output_type: str
    content: str | None = None
    stage: str = "generation"
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    warnings: list[Any] = field(default_factory=list)
    errors: list[Any] = field(default_factory=list)
    request_id: str | None = None
    workflow_run_id: str | None = None
    document_id: str | None = None
    template_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)