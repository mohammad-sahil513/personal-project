"""
Dependency checker for the Generation module.

Responsibilities:
- Evaluate section dependency readiness
- Identify runnable (ready) sections
- Support dependency-wave execution planning

Important:
- This file contains pure dependency logic only.
- It does NOT execute sections.
- It does NOT mutate session state.
"""

from __future__ import annotations

from typing import Iterable

from backend.modules.generation.contracts.session_contracts import (
    SectionDependencyState,
    SectionRuntimeState,
)
from backend.modules.generation.contracts.generation_contracts import (
    SectionExecutionStatus,
)


class DependencyChecker:
    """
    Evaluates section dependency readiness.
    """

    TERMINAL_STATUSES = {
        SectionExecutionStatus.GENERATED,
        SectionExecutionStatus.DEGRADED,
        SectionExecutionStatus.SKIPPED,
        SectionExecutionStatus.FAILED,
    }

    def is_dependency_satisfied(
        self,
        section: SectionRuntimeState,
        completed_section_ids: set[str],
    ) -> bool:
        """
        Return True if all dependencies of the section are satisfied.
        """
        if not section.dependency_ids:
            return True

        return all(dep_id in completed_section_ids for dep_id in section.dependency_ids)

    def update_dependency_state(
        self,
        section: SectionRuntimeState,
        completed_section_ids: set[str],
    ) -> SectionDependencyState:
        """
        Determine and return the correct dependency state for a section.
        """
        if self.is_dependency_satisfied(section, completed_section_ids):
            return SectionDependencyState.SATISFIED

        return SectionDependencyState.BLOCKED

    def find_ready_sections(
        self,
        sections: Iterable[SectionRuntimeState],
        completed_section_ids: set[str],
    ) -> list[SectionRuntimeState]:
        """
        Return all sections that:
        - are dependency-satisfied
        - are not yet running
        - are not yet in a terminal state
        """
        ready: list[SectionRuntimeState] = []

        for section in sections:
            if section.status in self.TERMINAL_STATUSES:
                continue

            if section.status == SectionExecutionStatus.RUNNING:
                continue

            if self.is_dependency_satisfied(section, completed_section_ids):
                ready.append(section)

        return ready

    def compute_dependency_wave(
        self,
        sections: Iterable[SectionRuntimeState],
    ) -> list[list[str]]:
        """
        Compute dependency waves for the given sections.

        Each wave contains section_ids that can execute together.
        """
        remaining = {s.section_id: s for s in sections}
        completed: set[str] = set()
        waves: list[list[str]] = []

        while remaining:
            ready_in_wave: list[str] = []

            for section_id, section in list(remaining.items()):
                if self.is_dependency_satisfied(section, completed):
                    ready_in_wave.append(section_id)

            if not ready_in_wave:
                # Circular or unsatisfiable dependency detected
                raise ValueError(
                    "Circular or unsatisfiable dependency graph detected."
                )

            waves.append(ready_in_wave)

            for section_id in ready_in_wave:
                completed.add(section_id)
                remaining.pop(section_id)

        return waves