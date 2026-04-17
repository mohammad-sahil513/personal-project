"""
Tests for DependencySorterService.
"""

from __future__ import annotations

import pytest

from backend.modules.template.contracts.section_contracts import (
    TemplateSection,
)
from backend.modules.template.contracts.template_contracts import PromptReference
from backend.modules.template.models.template_enums import GenerationStrategy
from backend.modules.template.services.dependency_sorter_service import DependencySorterService


def _create_section(section_id: str, dependencies: list[str]) -> TemplateSection:
    return TemplateSection(
        section_id=section_id,
        title=f"Section {section_id}",
        generation_strategy=GenerationStrategy.SUMMARIZE_TEXT,
        prompt=PromptReference(prompt_key="default", slots_required=["source_evidence"]),
        dependencies=dependencies,
    )


def test_dependency_sort_valid():
    sorter = DependencySorterService()
    
    sections = [
        _create_section("C", ["B"]),
        _create_section("A", []),
        _create_section("B", ["A"]),
    ]
    
    sorted_sections = sorter.sort_sections(sections)
    
    # A has no deps, so it goes first.
    # B depends on A.
    # C depends on B.
    sorted_ids = [s.section_id for s in sorted_sections]
    assert sorted_ids == ["A", "B", "C"]


def test_dependency_sort_missing_dependency():
    sorter = DependencySorterService()
    
    sections = [
        _create_section("A", ["GHOST"]),
    ]
    
    with pytest.raises(ValueError, match="Unknown dependency reference"):
        sorter.sort_sections(sections)


def test_dependency_sort_cycle_detected():
    sorter = DependencySorterService()
    
    # A depends on B, B depends on C, C depends on A.
    sections = [
        _create_section("A", ["B"]),
        _create_section("B", ["C"]),
        _create_section("C", ["A"]),
    ]
    
    with pytest.raises(ValueError, match="Dependency cycle detected"):
        sorter.sort_sections(sections)
