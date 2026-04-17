"""
Unit tests — Phase 5.1
Covers: generation_contracts, generation_config, session_contracts.
All tests are purely deterministic with no external dependencies.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.modules.generation.contracts.generation_contracts import (
    DiagramArtifactRefs,
    GenerationJobStatus,
    GenerationStrategy,
    GenerationWarningCode,
    OutputType,
    SectionExecutionStatus,
    SectionGenerationResult,
    SectionOutput,
)
from backend.modules.generation.contracts.session_contracts import (
    GenerationSessionState,
    SectionDependencyState,
    SectionRuntimeState,
    SnapshotMetadata,
    SnapshotScope,
    WaveExecutionState,
)
from backend.modules.generation.models.generation_config import (
    DEFAULT_GENERATION_CONFIG,
    GenerationConfig,
)


# ---------------------------------------------------------------------------
# SectionOutput
# ---------------------------------------------------------------------------

class TestSectionOutput:
    def test_markdown_text_happy_path(self):
        output = SectionOutput(
            output_type=OutputType.MARKDOWN_TEXT,
            content_markdown="## Overview\n\nThis system uses OAuth 2.0.",
        )
        assert output.content_markdown is not None

    def test_markdown_table_happy_path(self):
        output = SectionOutput(
            output_type=OutputType.MARKDOWN_TABLE,
            content_markdown="| Col | Val |\n|-----|-----|\n| A   | B   |",
        )
        assert output.output_type == OutputType.MARKDOWN_TABLE

    def test_markdown_text_without_content_raises(self):
        with pytest.raises(ValidationError):
            SectionOutput(output_type=OutputType.MARKDOWN_TEXT)

    def test_markdown_text_blank_content_raises(self):
        with pytest.raises(ValidationError):
            SectionOutput(output_type=OutputType.MARKDOWN_TEXT, content_markdown="   ")

    def test_markdown_text_with_diagram_artifacts_raises(self):
        with pytest.raises(ValidationError):
            SectionOutput(
                output_type=OutputType.MARKDOWN_TEXT,
                content_markdown="Some content.",
                diagram_artifacts=DiagramArtifactRefs(puml_path="path/to/file.puml"),
            )

    def test_diagram_artifact_happy_path(self):
        output = SectionOutput(
            output_type=OutputType.DIAGRAM_ARTIFACT,
            diagram_artifacts=DiagramArtifactRefs(puml_path="path/to/diagram.puml"),
        )
        assert output.diagram_artifacts is not None

    def test_diagram_artifact_without_refs_raises(self):
        with pytest.raises(ValidationError):
            SectionOutput(output_type=OutputType.DIAGRAM_ARTIFACT)

    def test_metadata_optional(self):
        output = SectionOutput(
            output_type=OutputType.MARKDOWN_TEXT,
            content_markdown="Some content.",
            metadata={"custom_key": "custom_value"},
        )
        assert output.metadata["custom_key"] == "custom_value"

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            SectionOutput(
                output_type=OutputType.MARKDOWN_TEXT,
                content_markdown="Content.",
                unknown_field="bad",
            )


# ---------------------------------------------------------------------------
# SectionGenerationResult
# ---------------------------------------------------------------------------

def _make_text_output() -> SectionOutput:
    return SectionOutput(
        output_type=OutputType.MARKDOWN_TEXT,
        content_markdown="## Overview\n\nContent here.",
    )


def _make_result(
    section_id: str = "sec_001",
    status: SectionExecutionStatus = SectionExecutionStatus.GENERATED,
    strategy: GenerationStrategy = GenerationStrategy.SUMMARIZE_TEXT,
    output: SectionOutput | None = None,
    error_message: str | None = None,
    low_evidence: bool = False,
    manual_review_required: bool = False,
) -> SectionGenerationResult:
    if output is None and status in {
        SectionExecutionStatus.GENERATED,
        SectionExecutionStatus.DEGRADED,
    }:
        output = _make_text_output()
    return SectionGenerationResult(
        section_id=section_id,
        strategy=strategy,
        status=status,
        output=output,
        error_message=error_message,
        low_evidence=low_evidence,
        manual_review_required=manual_review_required,
    )


class TestSectionGenerationResult:
    def test_generated_status_requires_output(self):
        with pytest.raises(ValidationError):
            SectionGenerationResult(
                section_id="s1",
                strategy=GenerationStrategy.SUMMARIZE_TEXT,
                status=SectionExecutionStatus.GENERATED,
                output=None,
            )

    def test_degraded_status_requires_output(self):
        with pytest.raises(ValidationError):
            SectionGenerationResult(
                section_id="s1",
                strategy=GenerationStrategy.SUMMARIZE_TEXT,
                status=SectionExecutionStatus.DEGRADED,
                output=None,
            )

    def test_failed_status_requires_error_message(self):
        with pytest.raises(ValidationError):
            SectionGenerationResult(
                section_id="s1",
                strategy=GenerationStrategy.SUMMARIZE_TEXT,
                status=SectionExecutionStatus.FAILED,
            )

    def test_failed_with_error_message_valid(self):
        result = SectionGenerationResult(
            section_id="s1",
            strategy=GenerationStrategy.SUMMARIZE_TEXT,
            status=SectionExecutionStatus.FAILED,
            error_message="LLM timeout.",
        )
        assert result.error_message == "LLM timeout."

    def test_low_evidence_requires_manual_review(self):
        with pytest.raises(ValidationError):
            _make_result(low_evidence=True, manual_review_required=False)

    def test_low_evidence_with_manual_review_valid(self):
        result = _make_result(
            low_evidence=True,
            manual_review_required=True,
            status=SectionExecutionStatus.DEGRADED,
        )
        assert result.low_evidence is True

    def test_completed_at_only_for_terminal_statuses(self):
        with pytest.raises(ValidationError):
            SectionGenerationResult(
                section_id="s1",
                strategy=GenerationStrategy.SUMMARIZE_TEXT,
                status=SectionExecutionStatus.RUNNING,
                completed_at=datetime.now(timezone.utc),
            )

    def test_skipped_status_no_output_required(self):
        result = SectionGenerationResult(
            section_id="s1",
            strategy=GenerationStrategy.SUMMARIZE_TEXT,
            status=SectionExecutionStatus.SKIPPED,
        )
        assert result.output is None


# ---------------------------------------------------------------------------
# GenerationConfig
# ---------------------------------------------------------------------------

class TestGenerationConfig:
    def test_defaults_valid(self):
        cfg = GenerationConfig()
        assert cfg.max_prompt_tokens == 3000
        assert cfg.max_source_facts == 8
        assert cfg.max_tables == 2
        assert cfg.max_conflicts == 3
        assert cfg.max_rolling_context_sections == 2
        assert cfg.max_retries == 2
        assert cfg.snapshot_after_each_section is True
        assert cfg.enable_wave_execution is True

    def test_custom_overrides(self):
        cfg = GenerationConfig(max_prompt_tokens=1000, max_retries=0)
        assert cfg.max_prompt_tokens == 1000
        assert cfg.max_retries == 0

    def test_negative_top_k_raises(self):
        with pytest.raises(ValidationError):
            GenerationConfig(max_source_facts=0)

    def test_max_prompt_tokens_must_be_positive(self):
        with pytest.raises(ValidationError):
            GenerationConfig(max_prompt_tokens=0)

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            GenerationConfig(unknown_param=999)

    def test_default_singleton_matches_module_constants(self):
        from backend.modules.generation.models.generation_config import (
            MAX_SOURCE_FACTS,
            MAX_TABLES,
            MAX_PROMPT_TOKENS,
        )
        assert MAX_SOURCE_FACTS == DEFAULT_GENERATION_CONFIG.max_source_facts
        assert MAX_TABLES == DEFAULT_GENERATION_CONFIG.max_tables
        assert MAX_PROMPT_TOKENS == DEFAULT_GENERATION_CONFIG.max_prompt_tokens


# ---------------------------------------------------------------------------
# SnapshotMetadata
# ---------------------------------------------------------------------------

class TestSnapshotMetadata:
    def test_section_scope_requires_section_id(self):
        with pytest.raises(ValidationError):
            SnapshotMetadata(
                snapshot_id="snap_1",
                scope=SnapshotScope.SECTION,
                path="blob/path",
            )

    def test_wave_scope_requires_wave_index(self):
        with pytest.raises(ValidationError):
            SnapshotMetadata(
                snapshot_id="snap_2",
                scope=SnapshotScope.WAVE,
                path="blob/path",
            )

    def test_job_scope_happy_path(self):
        snap = SnapshotMetadata(
            snapshot_id="snap_3",
            scope=SnapshotScope.JOB,
            path="blob/path/job_snap.json",
        )
        assert snap.scope == SnapshotScope.JOB

    def test_section_scope_happy_path(self):
        snap = SnapshotMetadata(
            snapshot_id="snap_4",
            scope=SnapshotScope.SECTION,
            path="blob/path.json",
            related_section_id="sec_001",
        )
        assert snap.related_section_id == "sec_001"

    def test_revision_default_is_1(self):
        snap = SnapshotMetadata(
            snapshot_id="snap_5",
            scope=SnapshotScope.JOB,
            path="path",
        )
        assert snap.revision == 1

    def test_revision_below_1_raises(self):
        with pytest.raises(ValidationError):
            SnapshotMetadata(
                snapshot_id="snap_6",
                scope=SnapshotScope.JOB,
                path="path",
                revision=0,
            )


# ---------------------------------------------------------------------------
# WaveExecutionState
# ---------------------------------------------------------------------------

class TestWaveExecutionState:
    def test_happy_path(self):
        wave = WaveExecutionState(
            wave_index=0,
            ready_section_ids=["sec_001", "sec_002"],
        )
        assert len(wave.ready_section_ids) == 2

    def test_section_id_in_multiple_buckets_raises(self):
        with pytest.raises(ValidationError):
            WaveExecutionState(
                wave_index=0,
                ready_section_ids=["sec_001"],
                running_section_ids=["sec_001"],   # duplicated!
            )

    def test_same_wave_index_across_instances_allowed(self):
        w1 = WaveExecutionState(wave_index=0, ready_section_ids=["sec_001"])
        w2 = WaveExecutionState(wave_index=0, ready_section_ids=["sec_002"])
        assert w1.wave_index == w2.wave_index


# ---------------------------------------------------------------------------
# SectionRuntimeState
# ---------------------------------------------------------------------------

class TestSectionRuntimeState:
    def _make_state(
        self,
        status: SectionExecutionStatus = SectionExecutionStatus.PENDING,
        result: SectionGenerationResult | None = None,
    ) -> SectionRuntimeState:
        return SectionRuntimeState(
            section_id="sec_001",
            strategy=GenerationStrategy.SUMMARIZE_TEXT,
            status=status,
            result=result,
        )

    def test_pending_state_happy_path(self):
        state = self._make_state()
        assert state.status == SectionExecutionStatus.PENDING
        assert state.result is None

    def test_terminal_state_requires_result(self):
        with pytest.raises(ValidationError):
            SectionRuntimeState(
                section_id="sec_001",
                strategy=GenerationStrategy.SUMMARIZE_TEXT,
                status=SectionExecutionStatus.GENERATED,
                result=None,
            )

    def test_result_section_id_must_match(self):
        result = _make_result(section_id="sec_999")
        with pytest.raises(ValidationError):
            SectionRuntimeState(
                section_id="sec_001",
                strategy=GenerationStrategy.SUMMARIZE_TEXT,
                status=SectionExecutionStatus.GENERATED,
                result=result,
            )

    def test_result_strategy_must_match(self):
        result = _make_result(
            section_id="sec_001",
            strategy=GenerationStrategy.GENERATE_TABLE,
            status=SectionExecutionStatus.GENERATED,
        )
        with pytest.raises(ValidationError):
            SectionRuntimeState(
                section_id="sec_001",
                strategy=GenerationStrategy.SUMMARIZE_TEXT,   # mismatch
                status=SectionExecutionStatus.GENERATED,
                result=result,
            )

    def test_completed_at_only_for_terminal(self):
        with pytest.raises(ValidationError):
            SectionRuntimeState(
                section_id="sec_001",
                strategy=GenerationStrategy.SUMMARIZE_TEXT,
                status=SectionExecutionStatus.RUNNING,
                completed_at=datetime.now(timezone.utc),
            )


# ---------------------------------------------------------------------------
# GenerationSessionState
# ---------------------------------------------------------------------------

class TestGenerationSessionState:
    def _make_session(self, **overrides) -> GenerationSessionState:
        defaults = {
            "job_id": "job_001",
            "document_id": "doc_001",
            "template_id": "tpl_001",
        }
        defaults.update(overrides)
        return GenerationSessionState(**defaults)

    def test_defaults_valid(self):
        session = self._make_session()
        assert session.job_status == GenerationJobStatus.ACCEPTED
        assert session.section_states == {}

    def test_section_states_key_must_match_embedded_id(self):
        result = _make_result(section_id="sec_001")
        state = SectionRuntimeState(
            section_id="sec_001",
            strategy=GenerationStrategy.SUMMARIZE_TEXT,
            status=SectionExecutionStatus.GENERATED,
            result=result,
        )
        with pytest.raises(ValidationError):
            # Key "wrong_key" doesn't match embedded section_id "sec_001"
            GenerationSessionState(
                job_id="j1",
                document_id="d1",
                template_id="t1",
                section_states={"wrong_key": state},
            )

    def test_diagram_index_unknown_section_raises(self):
        with pytest.raises(ValidationError):
            GenerationSessionState(
                job_id="j1",
                document_id="d1",
                template_id="t1",
                diagram_artifact_index={"unknown_sec": DiagramArtifactRefs()},
                section_states={},
            )

    def test_current_wave_index_without_wave_states_raises(self):
        with pytest.raises(ValidationError):
            GenerationSessionState(
                job_id="j1",
                document_id="d1",
                template_id="t1",
                current_wave_index=0,
                wave_states=[],
            )
