"""
Application service for section-level workflow progress.
"""

from __future__ import annotations

from backend.application.dto.section_progress_dto import (
    SectionProgressDTO,
    SectionProgressItemDTO,
)
from backend.core.exceptions import ValidationError

SECTION_STATUS_NOT_STARTED = "NOT_STARTED"
SECTION_STATUS_RUNNING = "RUNNING"
SECTION_STATUS_COMPLETED = "COMPLETED"
SECTION_STATUS_FAILED = "FAILED"
SECTION_STATUS_SKIPPED = "SKIPPED"


class SectionProgressService:
    """
    Backend use-case service for initializing and maintaining section progress state.
    """

    def initialize_from_section_plan(self, section_plan: dict) -> SectionProgressDTO:
        if not section_plan:
            raise ValidationError(
                message="section_plan is required to initialize section progress",
                error_code="SECTION_PROGRESS_INVALID",
                details={"field": "section_plan"},
            )

        sections = section_plan.get("sections")
        if sections is None:
            raise ValidationError(
                message="section_plan.sections is required",
                error_code="SECTION_PROGRESS_INVALID",
                details={"field": "sections"},
            )

        items = [
            SectionProgressItemDTO(
                section_id=item["section_id"],
                title=item["title"],
                execution_order=item["execution_order"],
                generation_strategy=item["generation_strategy"],
                retrieval_profile=item["retrieval_profile"],
                status=SECTION_STATUS_NOT_STARTED,
                progress_percent=0,
                dependencies=item.get("dependencies", []),
                metadata=item.get("metadata", {}),
            )
            for item in sections
        ]

        return self._build_progress(items)

    def mark_section_running(self, section_progress: dict, section_id: str) -> SectionProgressDTO:
        items = self._clone_items(section_progress)
        target = self._find_item(items, section_id)
        target.status = SECTION_STATUS_RUNNING
        target.progress_percent = max(target.progress_percent, 1)
        return self._build_progress(items)

    def mark_section_completed(self, section_progress: dict, section_id: str) -> SectionProgressDTO:
        items = self._clone_items(section_progress)
        target = self._find_item(items, section_id)
        target.status = SECTION_STATUS_COMPLETED
        target.progress_percent = 100
        return self._build_progress(items)

    def mark_section_failed(self, section_progress: dict, section_id: str, progress_percent: int = 0) -> SectionProgressDTO:
        items = self._clone_items(section_progress)
        target = self._find_item(items, section_id)
        target.status = SECTION_STATUS_FAILED
        target.progress_percent = progress_percent
        return self._build_progress(items)

    def _build_progress(self, items: list[SectionProgressItemDTO]) -> SectionProgressDTO:
        completed_sections = sum(1 for item in items if item.status == SECTION_STATUS_COMPLETED)
        running_sections = sum(1 for item in items if item.status == SECTION_STATUS_RUNNING)
        failed_sections = sum(1 for item in items if item.status == SECTION_STATUS_FAILED)

        return SectionProgressDTO(
            total_sections=len(items),
            completed_sections=completed_sections,
            running_sections=running_sections,
            failed_sections=failed_sections,
            sections=items,
        )

    def _clone_items(self, section_progress: dict) -> list[SectionProgressItemDTO]:
        items = section_progress.get("sections")
        if items is None:
            raise ValidationError(
                message="section_progress.sections is required",
                error_code="SECTION_PROGRESS_INVALID",
                details={"field": "sections"},
            )

        cloned: list[SectionProgressItemDTO] = []
        for item in items:
            cloned.append(
                SectionProgressItemDTO(
                    section_id=item["section_id"],
                    title=item["title"],
                    execution_order=item["execution_order"],
                    generation_strategy=item["generation_strategy"],
                    retrieval_profile=item["retrieval_profile"],
                    status=item["status"],
                    progress_percent=item["progress_percent"],
                    dependencies=item.get("dependencies", []),
                    metadata=item.get("metadata", {}),
                )
            )
        return cloned

    def _find_item(self, items: list[SectionProgressItemDTO], section_id: str) -> SectionProgressItemDTO:
        for item in items:
            if item.section_id == section_id:
                return item

        raise ValidationError(
            message="section_id not found in section progress",
            error_code="SECTION_PROGRESS_INVALID",
            details={"section_id": section_id},
        )
    def calculate_overall_progress_percent(self, section_progress: dict) -> int:
        """
        Calculate workflow-level progress based on completed sections.
        """
        total = section_progress.get("total_sections", 0)
        completed = section_progress.get("completed_sections", 0)

        if total <= 0:
            return 0

        return int((completed / total) * 100)