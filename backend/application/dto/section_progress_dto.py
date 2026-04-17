"""
Application DTOs for workflow-owned section progress state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class SectionProgressItemDTO:
    section_id: str
    title: str
    execution_order: int
    generation_strategy: str
    retrieval_profile: str
    status: str
    progress_percent: int
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class SectionProgressDTO:
    total_sections: int
    completed_sections: int
    running_sections: int
    failed_sections: int
    sections: list[SectionProgressItemDTO] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_sections": self.total_sections,
            "completed_sections": self.completed_sections,
            "running_sections": self.running_sections,
            "failed_sections": self.failed_sections,
            "sections": [section.to_dict() for section in self.sections],
        }