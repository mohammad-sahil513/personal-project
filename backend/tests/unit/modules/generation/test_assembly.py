"""
Unit tests — Phase 5.4 (dependency_checker, section_assembler, toc_generator)
All components are purely deterministic with no external dependencies.
"""

from __future__ import annotations

import pytest

from backend.modules.generation.assembly.section_assembler import (
    AssembledSection,
    SectionAssembler,
    SectionAssemblyRequest,
)
from backend.modules.generation.assembly.toc_generator import (
    TOCGenerationRequest,
    TOCGenerator,
)
from backend.modules.generation.contracts.generation_contracts import (
    DiagramArtifactRefs,
    GenerationStrategy,
    OutputType,
    SectionExecutionStatus,
    SectionGenerationResult,
    SectionOutput,
)
from backend.modules.generation.contracts.session_contracts import (
    SectionDependencyState,
    SectionRuntimeState,
)
from backend.modules.generation.orchestrators.dependency_checker import DependencyChecker


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _make_text_output(content: str = "## Overview\n\nContent.") -> SectionOutput:
    return SectionOutput(output_type=OutputType.MARKDOWN_TEXT, content_markdown=content)


def _make_table_output() -> SectionOutput:
    return SectionOutput(
        output_type=OutputType.MARKDOWN_TABLE,
        content_markdown="| Col |\n|-----|\n| Val |",
    )


def _make_diagram_output() -> SectionOutput:
    return SectionOutput(
        output_type=OutputType.DIAGRAM_ARTIFACT,
        diagram_artifacts=DiagramArtifactRefs(puml_path="path/to/diagram.puml"),
    )


def _make_result(
    section_id: str,
    status: SectionExecutionStatus,
    strategy: GenerationStrategy = GenerationStrategy.SUMMARIZE_TEXT,
    output: SectionOutput | None = None,
    heading: str | None = None,
    error_message: str | None = None,
) -> SectionGenerationResult:
    if output is None and status in {SectionExecutionStatus.GENERATED, SectionExecutionStatus.DEGRADED}:
        output = _make_text_output()
    if status == SectionExecutionStatus.FAILED and error_message is None:
        error_message = "Generation failed."
    return SectionGenerationResult(
        section_id=section_id,
        section_heading=heading or section_id,
        strategy=strategy,
        status=status,
        output=output,
        error_message=error_message,
    )


def _make_runtime_state(
    section_id: str,
    status: SectionExecutionStatus = SectionExecutionStatus.PENDING,
    dependency_ids: list[str] | None = None,
) -> SectionRuntimeState:
    result = None
    if status in {
        SectionExecutionStatus.GENERATED,
        SectionExecutionStatus.DEGRADED,
        SectionExecutionStatus.SKIPPED,
        SectionExecutionStatus.FAILED,
    }:
        result = _make_result(section_id=section_id, status=status)
    return SectionRuntimeState(
        section_id=section_id,
        strategy=GenerationStrategy.SUMMARIZE_TEXT,
        status=status,
        dependency_ids=dependency_ids or [],
        result=result,
    )


# ---------------------------------------------------------------------------
# DependencyChecker
# ---------------------------------------------------------------------------

class TestDependencyChecker:
    def setup_method(self):
        self.checker = DependencyChecker()

    def test_no_dependencies_always_satisfied(self):
        state = _make_runtime_state("sec_001")
        assert self.checker.is_dependency_satisfied(state, completed_section_ids=set()) is True

    def test_dependency_in_completed_set_satisfied(self):
        state = _make_runtime_state("sec_002", dependency_ids=["sec_001"])
        assert self.checker.is_dependency_satisfied(state, completed_section_ids={"sec_001"}) is True

    def test_dependency_not_in_completed_set_blocked(self):
        state = _make_runtime_state("sec_002", dependency_ids=["sec_001"])
        assert self.checker.is_dependency_satisfied(state, completed_section_ids=set()) is False

    def test_find_ready_sections_returns_pending_with_satisfied_deps(self):
        s1 = _make_runtime_state("sec_001")        # no deps
        s2 = _make_runtime_state("sec_002", dependency_ids=["sec_001"])  # blocked
        ready = self.checker.find_ready_sections([s1, s2], completed_section_ids=set())
        ready_ids = [s.section_id for s in ready]
        assert "sec_001" in ready_ids
        assert "sec_002" not in ready_ids

    def test_find_ready_excludes_terminal_sections(self):
        s_done = _make_runtime_state("sec_001", status=SectionExecutionStatus.GENERATED)
        ready = self.checker.find_ready_sections([s_done], completed_section_ids={"sec_001"})
        assert ready == []

    def test_find_ready_excludes_running_sections(self):
        s_running = _make_runtime_state("sec_001", status=SectionExecutionStatus.RUNNING)
        ready = self.checker.find_ready_sections([s_running], completed_section_ids=set())
        assert ready == []

    def test_compute_dependency_wave_linear(self):
        s1 = _make_runtime_state("sec_001")
        s2 = _make_runtime_state("sec_002", dependency_ids=["sec_001"])
        s3 = _make_runtime_state("sec_003", dependency_ids=["sec_002"])
        waves = self.checker.compute_dependency_wave([s1, s2, s3])
        assert waves[0] == ["sec_001"]
        assert waves[1] == ["sec_002"]
        assert waves[2] == ["sec_003"]

    def test_compute_dependency_wave_parallel_first_wave(self):
        s1 = _make_runtime_state("sec_001")
        s2 = _make_runtime_state("sec_002")        # also no deps
        s3 = _make_runtime_state("sec_003", dependency_ids=["sec_001", "sec_002"])
        waves = self.checker.compute_dependency_wave([s1, s2, s3])
        # Wave 0 should contain both independent sections
        assert set(waves[0]) == {"sec_001", "sec_002"}
        assert waves[1] == ["sec_003"]

    def test_circular_dependency_raises(self):
        s1 = _make_runtime_state("sec_001", dependency_ids=["sec_002"])
        s2 = _make_runtime_state("sec_002", dependency_ids=["sec_001"])
        with pytest.raises(ValueError, match="[Cc]ircular"):
            self.checker.compute_dependency_wave([s1, s2])


# ---------------------------------------------------------------------------
# SectionAssembler
# ---------------------------------------------------------------------------

class TestSectionAssembler:
    def setup_method(self):
        self.assembler = SectionAssembler()

    def _assemble(self, results: list[SectionGenerationResult], order: list[str] | None = None, **kwargs):
        if order is None:
            order = [r.section_id for r in results]
        return self.assembler.assemble(
            SectionAssemblyRequest(
                ordered_section_ids=order,
                section_results=results,
                **kwargs,
            )
        )

    def test_generated_section_included(self):
        r = _make_result("sec_001", SectionExecutionStatus.GENERATED)
        result = self._assemble([r])
        assert result.included_section_count == 1
        assert result.assembled_sections[0].included is True

    def test_degraded_section_included_by_default(self):
        r = _make_result("sec_001", SectionExecutionStatus.DEGRADED)
        result = self._assemble([r])
        assert result.assembled_sections[0].included is True

    def test_degraded_section_omitted_when_flag_false(self):
        r = _make_result("sec_001", SectionExecutionStatus.DEGRADED)
        result = self._assemble([r], include_degraded_sections=False)
        assert result.assembled_sections[0].included is False

    def test_skipped_section_produces_placeholder_by_default(self):
        r = _make_result("sec_001", SectionExecutionStatus.SKIPPED)
        result = self._assemble([r])
        section = result.assembled_sections[0]
        assert section.included is True
        assert section.placeholder_reason == "skipped"
        assert "[PLACEHOLDER]" in (section.markdown_content or "")

    def test_skipped_section_omitted_when_flag_false(self):
        r = _make_result("sec_001", SectionExecutionStatus.SKIPPED)
        result = self._assemble([r], include_skipped_placeholders=False)
        assert result.assembled_sections[0].included is False

    def test_failed_section_produces_placeholder_by_default(self):
        r = _make_result("sec_001", SectionExecutionStatus.FAILED)
        result = self._assemble([r])
        section = result.assembled_sections[0]
        assert section.included is True
        assert section.placeholder_reason == "failed"

    def test_failed_section_omitted_when_flag_false(self):
        r = _make_result("sec_001", SectionExecutionStatus.FAILED)
        result = self._assemble([r], include_failed_placeholders=False)
        assert result.assembled_sections[0].included is False

    def test_template_order_preserved(self):
        r1 = _make_result("sec_001", SectionExecutionStatus.GENERATED)
        r2 = _make_result("sec_002", SectionExecutionStatus.GENERATED)
        r3 = _make_result("sec_003", SectionExecutionStatus.GENERATED)
        result = self._assemble([r3, r1, r2], order=["sec_001", "sec_002", "sec_003"])
        ids = [s.section_id for s in result.assembled_sections]
        assert ids == ["sec_001", "sec_002", "sec_003"]

    def test_diagram_section_marker_block_generated(self):
        r = _make_result("sec_dia", SectionExecutionStatus.GENERATED, output=_make_diagram_output())
        result = self._assemble([r])
        section = result.assembled_sections[0]
        assert section.diagram_artifacts is not None
        assert "[[DIAGRAM:sec_dia]]" in (section.markdown_content or "")
        assert result.diagram_section_count == 1

    def test_assembled_markdown_joins_content(self):
        r1 = _make_result("sec_001", SectionExecutionStatus.GENERATED, output=_make_text_output("First."))
        r2 = _make_result("sec_002", SectionExecutionStatus.GENERATED, output=_make_text_output("Second."))
        result = self._assemble([r1, r2])
        assert "First" in result.assembled_markdown
        assert "Second" in result.assembled_markdown

    def test_missing_section_id_in_results_silently_omitted(self):
        r = _make_result("sec_001", SectionExecutionStatus.GENERATED)
        # "sec_ghost" is in order but has no result
        result = self._assemble([r], order=["sec_001", "sec_ghost"])
        assert len(result.assembled_sections) == 1


# ---------------------------------------------------------------------------
# TOCGenerator
# ---------------------------------------------------------------------------

class TestTOCGenerator:
    def setup_method(self):
        self.generator = TOCGenerator()

    def _make_assembled(
        self,
        section_id: str,
        heading: str | None = None,
        included: bool = True,
        markdown_content: str | None = None,
        placeholder_reason: str | None = None,
    ) -> AssembledSection:
        return AssembledSection(
            section_id=section_id,
            section_heading=heading or section_id,
            status=SectionExecutionStatus.GENERATED,
            included=included,
            markdown_content=markdown_content or f"## {heading or section_id}\n\nContent.",
            placeholder_reason=placeholder_reason,
        )

    def test_basic_toc_generated(self):
        sections = [self._make_assembled("sec_001", heading="Introduction")]
        result = self.generator.generate(TOCGenerationRequest(assembled_sections=sections))
        assert len(result.toc_entries) == 1
        assert result.toc_entries[0].heading == "Introduction"

    def test_excluded_sections_not_in_toc(self):
        sections = [
            self._make_assembled("sec_001", heading="Introduction"),
            self._make_assembled("sec_002", heading="Excluded", included=False),
        ]
        result = self.generator.generate(TOCGenerationRequest(assembled_sections=sections))
        assert result.included_entry_count == 1
        ids = [e.section_id for e in result.toc_entries]
        assert "sec_002" not in ids

    def test_placeholder_sections_excluded_when_flag_false(self):
        sections = [
            self._make_assembled("sec_001", heading="Intro"),
            self._make_assembled("sec_002", heading="Skipped", placeholder_reason="skipped"),
        ]
        result = self.generator.generate(
            TOCGenerationRequest(assembled_sections=sections, include_placeholder_sections=False)
        )
        ids = [e.section_id for e in result.toc_entries]
        assert "sec_002" not in ids

    def test_toc_markdown_contains_heading(self):
        sections = [self._make_assembled("sec_001", heading="Architecture Overview")]
        result = self.generator.generate(TOCGenerationRequest(assembled_sections=sections))
        assert "Architecture Overview" in result.toc_markdown

    def test_h3_heading_inferred_from_content(self):
        section = self._make_assembled(
            "sec_001",
            heading="Sub",
            markdown_content="### Sub-heading\n\nDetail.",
        )
        result = self.generator.generate(TOCGenerationRequest(assembled_sections=[section]))
        assert result.toc_entries[0].level == 3

    def test_h2_heading_inferred_from_content(self):
        section = self._make_assembled(
            "sec_001",
            heading="Top",
            markdown_content="## Top-level\n\nDetail.",
        )
        result = self.generator.generate(TOCGenerationRequest(assembled_sections=[section]))
        assert result.toc_entries[0].level == 2

    def test_anchor_slugified(self):
        section = self._make_assembled("sec_001", heading="My Section (Special!)") 
        result = self.generator.generate(TOCGenerationRequest(assembled_sections=[section]))
        anchor = result.toc_entries[0].anchor
        # Should be lowercase with hyphens, no parens
        assert "(" not in anchor
        assert anchor == anchor.lower()

    def test_toc_order_preserves_input_order(self):
        sections = [
            self._make_assembled("sec_001", heading="First"),
            self._make_assembled("sec_002", heading="Second"),
            self._make_assembled("sec_003", heading="Third"),
        ]
        result = self.generator.generate(TOCGenerationRequest(assembled_sections=sections))
        headings = [e.heading for e in result.toc_entries]
        assert headings == ["First", "Second", "Third"]

    def test_empty_sections_returns_empty_toc(self):
        result = self.generator.generate(TOCGenerationRequest(assembled_sections=[]))
        assert result.toc_entries == []
        assert result.toc_markdown == ""
