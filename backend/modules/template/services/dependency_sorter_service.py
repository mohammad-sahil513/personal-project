"""
Dependency sorter for template sections.

This service produces a deterministic topological ordering for template sections
based on declared dependencies.

Why this exists:
- downstream generation executes sections in dependency-aware order,
- the Template module should hand off a stable ordered section list,
- deterministic ordering improves testability and runtime predictability.

Ordering policy:
1. dependency constraints are always respected,
2. among sections that are currently ready, lower `order_hint` wins,
3. if `order_hint` is equal or missing, original declaration order wins,
4. section_id is used as a final stable tie-breaker.

Notes:
- Missing dependencies and dependency cycles are treated as hard errors.
- Validator service should normally catch missing references first, but this
  sorter still defends against invalid input to remain safe in isolation.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass

from ..contracts.section_contracts import TemplateSection


@dataclass(frozen=True, slots=True)
class _SortableSection:
    """Internal helper used for stable ordering of ready sections."""

    section: TemplateSection
    original_index: int

    @property
    def sort_key(self) -> tuple[int, int, str]:
        """
        Deterministic priority for ready sections.

        Lower values sort first.
        """
        order_hint = self.section.order_hint if self.section.order_hint is not None else 10**9
        return (order_hint, self.original_index, self.section.section_id)


class DependencySorterService:
    """Topological sorter with deterministic tie-breaking for template sections."""

    def sort_sections(self, sections: list[TemplateSection]) -> list[TemplateSection]:
        """
        Sort template sections into dependency-safe execution order.

        Args:
            sections: Unsorted template sections.

        Returns:
            Sections sorted in execution order.

        Raises:
            ValueError: If a dependency is missing or a cycle is detected.
        """
        if not sections:
            return []

        section_by_id = {section.section_id: section for section in sections}
        sortable_sections = {
            section.section_id: _SortableSection(section=section, original_index=index)
            for index, section in enumerate(sections)
        }

        self._validate_dependency_references(sections=sections, section_by_id=section_by_id)

        # Graph representation:
        # dependency -> dependent section
        adjacency: dict[str, list[str]] = {section.section_id: [] for section in sections}
        in_degree: dict[str, int] = {section.section_id: 0 for section in sections}

        for section in sections:
            for dependency in section.dependencies:
                adjacency[dependency].append(section.section_id)
                in_degree[section.section_id] += 1

        ready_heap: list[tuple[int, int, str, str]] = []
        for section_id, degree in in_degree.items():
            if degree == 0:
                sortable = sortable_sections[section_id]
                heapq.heappush(
                    ready_heap,
                    (*sortable.sort_key, section_id),
                )

        ordered_section_ids: list[str] = []

        while ready_heap:
            _, _, _, section_id = heapq.heappop(ready_heap)
            ordered_section_ids.append(section_id)

            for dependent_id in adjacency[section_id]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    sortable = sortable_sections[dependent_id]
                    heapq.heappush(
                        ready_heap,
                        (*sortable.sort_key, dependent_id),
                    )

        if len(ordered_section_ids) != len(sections):
            unresolved = sorted(
                section_id for section_id, degree in in_degree.items() if degree > 0
            )
            raise ValueError(
                "Dependency cycle detected among template sections: "
                f"{', '.join(unresolved)}"
            )

        return [section_by_id[section_id] for section_id in ordered_section_ids]

    @staticmethod
    def _validate_dependency_references(
        *,
        sections: list[TemplateSection],
        section_by_id: dict[str, TemplateSection],
    ) -> None:
        """Ensure every declared dependency exists before sorting begins."""
        missing: set[str] = set()

        for section in sections:
            for dependency in section.dependencies:
                if dependency not in section_by_id:
                    missing.add(dependency)

        if missing:
            raise ValueError(
                "Unknown dependency reference(s): "
                f"{', '.join(sorted(missing))}"
            )