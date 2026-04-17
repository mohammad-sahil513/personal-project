"""
Application DTOs for section-level retrieval results.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class RetrievalResultDTO:
    section_id: str
    retrieval_profile: str
    status: str
    overall_confidence: float
    stage: str = "retrieval"
    evidence_bundle: dict[str, Any] = field(default_factory=dict)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    warnings: list[Any] = field(default_factory=list)
    errors: list[Any] = field(default_factory=list)
    request_id: str | None = None
    workflow_run_id: str | None = None
    document_id: str | None = None
    template_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)