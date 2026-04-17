"""
Application DTOs for section execution planning.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class SectionPlanItemDTO:
    section_id: str
    title: str
    execution_order: int
    generation_strategy: str
    retrieval_profile: str
    dependencies: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(slots=True)
class SectionPlanDTO:
    template_id: str
    total_sections: int
    sections: list[SectionPlanItemDTO] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "total_sections": self.total_sections,
            "sections": [section.to_dict() for section in self.sections],
        }