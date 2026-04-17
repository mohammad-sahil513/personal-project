"""
Unit tests — Phase 7.1 (Pipeline Planners: section execution)
Covers SectionExecutionPlanner.
"""

from __future__ import annotations

import pytest

from backend.core.exceptions import ValidationError
from backend.pipeline.planners.section_execution_planner import SectionExecutionPlanner


class TestSectionExecutionPlanner:
    def setup_method(self):
        self.planner = SectionExecutionPlanner()

    def test_build_plan_happy_path(self):
        resolved = [
            {
                "section_id": "sec_02",
                "title": "Architecture",
                "execution_order": 2,
                "generation_strategy": "summarize_text",
            },
            {
                "section_id": "sec_01",
                "title": "Overview",
                "execution_order": 1,
            },
        ]

        plan = self.planner.build_plan(template_id="tpl_123", resolved_sections=resolved)

        assert plan.template_id == "tpl_123"
        assert plan.total_sections == 2
        # Verify ordering
        assert plan.sections[0].section_id == "sec_01"
        assert plan.sections[1].section_id == "sec_02"

        # Verify defaults
        assert plan.sections[0].generation_strategy == "summarize_text"
        # Since 'architecture' is not in 'Overview', default retrieval is 'default'
        assert plan.sections[0].retrieval_profile == "default"

        # Since 'architecture' IS in 'Architecture', retrieval is 'architecture'
        assert plan.sections[1].retrieval_profile == "architecture"

    def test_missing_template_id_raises(self):
        with pytest.raises(ValidationError, match="template_id"):
            self.planner.build_plan(template_id="", resolved_sections=[])

    def test_missing_resolved_sections_raises(self):
        with pytest.raises(ValidationError, match="resolved_sections"):
            self.planner.build_plan(template_id="tpl_123", resolved_sections=None) # type: ignore

    def test_missing_section_id_raises(self):
        with pytest.raises(ValidationError, match="section_id is required"):
            self.planner.build_plan(
                template_id="tpl_1",
                resolved_sections=[{"title": "Title", "execution_order": 1}],
            )

    def test_missing_execution_order_raises(self):
        with pytest.raises(ValidationError, match="execution_order is required"):
            self.planner.build_plan(
                template_id="tpl_1",
                resolved_sections=[{"section_id": "s1", "title": "Title"}],
            )

    def test_invalid_dependencies_raises(self):
        with pytest.raises(ValidationError, match="dependencies must be a list"):
            self.planner.build_plan(
                template_id="tpl_1",
                resolved_sections=[
                    {
                        "section_id": "s1",
                        "title": "Title",
                        "execution_order": 1,
                        "dependencies": "not a list",
                    }
                ],
            )

    def test_derive_retrieval_profiles(self):
        def _test_profile(title: str, strategy: str = "summarize_text") -> str:
            plan = self.planner.build_plan(
                template_id="tpl_1",
                resolved_sections=[
                    {
                        "section_id": "s1",
                        "title": title,
                        "execution_order": 1,
                        "generation_strategy": strategy,
                    }
                ],
            )
            return plan.sections[0].retrieval_profile

        assert _test_profile("Diagram", "diagram_plantuml") == "diagram"
        assert _test_profile("Table", "generate_table") == "table"
        assert _test_profile("System Architecture") == "architecture"
        assert _test_profile("System requirements") == "requirements"
        assert _test_profile("REST API Integration") == "api"
        assert _test_profile("Random topic") == "default"
