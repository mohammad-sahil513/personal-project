"""
Application DTOs for assembled document preview data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class AssembledSectionDTO:
    section_id: str
    title: str
    execution_order: int
    output_type: str
    content: str | None = None
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class AssembledDocumentDTO:
    workflow_run_id: str
    template_id: str | None
    total_sections: int
    title: str
    sections: list[AssembledSectionDTO] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "workflow_run_id": self.workflow_run_id,
            "template_id": self.template_id,
            "total_sections": self.total_sections,
            "title": self.title,
            "sections": [section.to_dict() for section in self.sections],
        }