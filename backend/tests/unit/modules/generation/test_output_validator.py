"""
Unit tests — Phase 5.3 (output_validator)
OutputValidator is fully deterministic with no external dependencies.
"""

from __future__ import annotations

import pytest

from backend.modules.generation.contracts.generation_contracts import (
    DiagramArtifactRefs,
    GenerationStrategy,
    OutputType,
    SectionOutput,
)
from backend.modules.generation.validators.output_validator import (
    OutputValidationRequest,
    OutputValidationRules,
    OutputValidator,
    ValidationIssueCode,
    ValidationIssueSeverity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TABLE = "| Stage | Action |\n|-------|--------|\n| 1     | Upload |"

def _make_text_output(content: str = "## Overview\n\nThis system authenticates via OAuth 2.0.") -> SectionOutput:
    return SectionOutput(output_type=OutputType.MARKDOWN_TEXT, content_markdown=content)


def _make_table_output(content: str = _VALID_TABLE) -> SectionOutput:
    return SectionOutput(output_type=OutputType.MARKDOWN_TABLE, content_markdown=content)


def _make_diagram_output(puml_path: str | None = "path/to/diagram.puml") -> SectionOutput:
    return SectionOutput(
        output_type=OutputType.DIAGRAM_ARTIFACT,
        diagram_artifacts=DiagramArtifactRefs(puml_path=puml_path),
    )


def _validate(
    output: SectionOutput,
    strategy: GenerationStrategy = GenerationStrategy.SUMMARIZE_TEXT,
    rules: OutputValidationRules | None = None,
    low_evidence: bool = False,
):
    validator = OutputValidator()
    return validator.validate(
        OutputValidationRequest(
            section_id="sec_001",
            strategy=strategy,
            output=output,
            rules=rules or OutputValidationRules(),
            low_evidence=low_evidence,
        )
    )


# ---------------------------------------------------------------------------
# Happy-path validations
# ---------------------------------------------------------------------------

class TestOutputValidatorHappyPath:
    def test_valid_text_output_passes(self):
        result = _validate(_make_text_output())
        assert result.is_valid is True
        assert result.issues == []

    def test_valid_table_output_passes(self):
        result = _validate(
            _make_table_output(),
            strategy=GenerationStrategy.GENERATE_TABLE,
        )
        assert result.is_valid is True

    def test_valid_diagram_output_passes(self):
        result = _validate(
            _make_diagram_output(),
            strategy=GenerationStrategy.DIAGRAM_PLANTUML,
        )
        assert result.is_valid is True

    def test_word_count_returned(self):
        result = _validate(_make_text_output("Word one two three four."))
        assert result.word_count == 5

    def test_table_row_count_returned(self):
        result = _validate(
            _make_table_output(),
            strategy=GenerationStrategy.GENERATE_TABLE,
        )
        assert result.table_row_count == 1

    def test_normalized_output_trims_whitespace(self):
        result = _validate(_make_text_output("   ## Title\n\nContent here.   "))
        assert not result.normalized_output.content_markdown.startswith(" ")


# ---------------------------------------------------------------------------
# Strategy ↔ output-type mismatch
# ---------------------------------------------------------------------------

class TestStrategyOutputTypeMismatch:
    def test_text_strategy_with_table_output_raises_error(self):
        result = _validate(
            _make_table_output(),
            strategy=GenerationStrategy.SUMMARIZE_TEXT,  # expects MARKDOWN_TEXT
        )
        assert any(i.code == ValidationIssueCode.STRATEGY_OUTPUT_MISMATCH for i in result.issues)
        assert result.is_valid is False

    def test_table_strategy_with_text_output_raises_error(self):
        result = _validate(
            _make_text_output(),
            strategy=GenerationStrategy.GENERATE_TABLE,
        )
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.STRATEGY_OUTPUT_MISMATCH in codes


# ---------------------------------------------------------------------------
# Markdown contract
# ---------------------------------------------------------------------------

class TestMarkdownContractValidation:
    def test_inline_html_not_allowed(self):
        result = _validate(_make_text_output("<b>Bold</b> text."))
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.MARKDOWN_INLINE_HTML_NOT_ALLOWED in codes

    def test_unbalanced_code_fence_detected(self):
        result = _validate(_make_text_output("```\nsome code\nno closing fence"))
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.MARKDOWN_UNBALANCED_CODE_FENCE in codes

    def test_balanced_code_fence_passes(self):
        result = _validate(_make_text_output("```\nsome code\n```"))
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.MARKDOWN_UNBALANCED_CODE_FENCE not in codes

    def test_nested_list_not_allowed(self):
        content = "Top item\n  - Nested item"
        result = _validate(_make_text_output(content))
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.MARKDOWN_NESTED_LIST_NOT_ALLOWED in codes

    def test_h1_heading_not_allowed(self):
        result = _validate(_make_text_output("# H1 Heading\n\nSome content."))
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.MARKDOWN_UNSUPPORTED_HEADING in codes

    def test_h2_heading_allowed(self):
        result = _validate(_make_text_output("## H2 Heading\n\nSome content."))
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.MARKDOWN_UNSUPPORTED_HEADING not in codes

    def test_h3_heading_allowed(self):
        result = _validate(_make_text_output("### H3 Heading\n\nSome content."))
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.MARKDOWN_UNSUPPORTED_HEADING not in codes

    def test_h4_heading_not_allowed(self):
        result = _validate(_make_text_output("#### H4 Too Deep\n\nContent."))
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.MARKDOWN_UNSUPPORTED_HEADING in codes


# ---------------------------------------------------------------------------
# Word-count rules
# ---------------------------------------------------------------------------

class TestWordCountRules:
    def test_min_words_not_met_raises_error(self):
        rules = OutputValidationRules(min_words=100)
        result = _validate(_make_text_output("Short content."), rules=rules)
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.TEXT_MIN_WORDS_NOT_MET in codes

    def test_max_words_exceeded_raises_error(self):
        content = " ".join(["word"] * 50)
        rules = OutputValidationRules(max_words=10)
        result = _validate(_make_text_output(content), rules=rules)
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.TEXT_MAX_WORDS_EXCEEDED in codes

    def test_within_word_bounds_passes(self):
        content = " ".join(["word"] * 20)
        rules = OutputValidationRules(min_words=5, max_words=50)
        result = _validate(_make_text_output(content), rules=rules)
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.TEXT_MIN_WORDS_NOT_MET not in codes
        assert ValidationIssueCode.TEXT_MAX_WORDS_EXCEEDED not in codes


# ---------------------------------------------------------------------------
# Banned phrases
# ---------------------------------------------------------------------------

class TestBannedPhrases:
    def test_banned_phrase_detected(self):
        rules = OutputValidationRules(banned_phrases=["not applicable"])
        result = _validate(_make_text_output("This section is not applicable."), rules=rules)
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.BANNED_PHRASE_FOUND in codes

    def test_banned_phrase_case_insensitive(self):
        rules = OutputValidationRules(banned_phrases=["N/A"])
        result = _validate(_make_text_output("Status: n/a"), rules=rules)
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.BANNED_PHRASE_FOUND in codes

    def test_no_banned_phrase_in_content_passes(self):
        rules = OutputValidationRules(banned_phrases=["forbidden phrase"])
        result = _validate(_make_text_output("Clean content about the system."), rules=rules)
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.BANNED_PHRASE_FOUND not in codes


# ---------------------------------------------------------------------------
# Low-evidence prefix
# ---------------------------------------------------------------------------

class TestLowEvidencePrefix:
    def test_low_evidence_prefix_required_when_flagged(self):
        result = _validate(_make_text_output("No prefix here."), low_evidence=True)
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.LOW_EVIDENCE_PREFIX_MISSING in codes

    def test_low_evidence_prefix_present_passes(self):
        result = _validate(_make_text_output("[LOW EVIDENCE] Content here."), low_evidence=True)
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.LOW_EVIDENCE_PREFIX_MISSING not in codes

    def test_rules_require_prefix_enforced(self):
        rules = OutputValidationRules(require_low_evidence_prefix=True)
        result = _validate(_make_text_output("No prefix."), rules=rules)
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.LOW_EVIDENCE_PREFIX_MISSING in codes


# ---------------------------------------------------------------------------
# Table validation
# ---------------------------------------------------------------------------

class TestTableValidation:
    def test_required_columns_all_present_passes(self):
        rules = OutputValidationRules(required_columns=["Stage", "Action"])
        result = _validate(_make_table_output(), strategy=GenerationStrategy.GENERATE_TABLE, rules=rules)
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.TABLE_REQUIRED_COLUMNS_MISSING not in codes

    def test_required_columns_missing_raises_error(self):
        rules = OutputValidationRules(required_columns=["Stage", "Missing Col"])
        result = _validate(_make_table_output(), strategy=GenerationStrategy.GENERATE_TABLE, rules=rules)
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.TABLE_REQUIRED_COLUMNS_MISSING in codes

    def test_min_rows_not_met_raises_error(self):
        rules = OutputValidationRules(min_rows=5)
        result = _validate(_make_table_output(), strategy=GenerationStrategy.GENERATE_TABLE, rules=rules)
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.TABLE_MIN_ROWS_NOT_MET in codes

    def test_table_not_found_when_no_pipe_chars(self):
        result = _validate(
            SectionOutput(output_type=OutputType.MARKDOWN_TABLE, content_markdown="Not a table at all."),
            strategy=GenerationStrategy.GENERATE_TABLE,
        )
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.TABLE_MARKDOWN_NOT_FOUND in codes


# ---------------------------------------------------------------------------
# Diagram validation
# ---------------------------------------------------------------------------

class TestDiagramValidation:
    def test_diagram_with_no_refs_raises_missing(self):
        output = SectionOutput(
            output_type=OutputType.DIAGRAM_ARTIFACT,
            diagram_artifacts=DiagramArtifactRefs(),   # no paths set
        )
        result = _validate(output, strategy=GenerationStrategy.DIAGRAM_PLANTUML)
        codes = [i.code for i in result.issues]
        assert ValidationIssueCode.DIAGRAM_ARTIFACT_MISSING in codes

    def test_diagram_with_puml_path_passes(self):
        result = _validate(_make_diagram_output(), strategy=GenerationStrategy.DIAGRAM_PLANTUML)
        assert result.is_valid is True

    def test_diagram_with_png_only_passes(self):
        output = SectionOutput(
            output_type=OutputType.DIAGRAM_ARTIFACT,
            diagram_artifacts=DiagramArtifactRefs(png_path="path/to/diagram.png"),
        )
        result = _validate(output, strategy=GenerationStrategy.DIAGRAM_PLANTUML)
        assert result.is_valid is True
