"""
Output validator for the Generation module.

Responsibilities:
- Validate strategy/output-type alignment
- Validate markdown contract compliance
- Validate template-like section rules (min/max words, required columns, min rows, banned phrases)
- Validate low-evidence prefix requirements
- Validate diagram artifact presence at a contract level

Important:
- This file performs validation only.
- It does NOT perform retry/correction.
- It does NOT call Retrieval or the LLM.
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.generation.contracts.generation_contracts import (
    GenerationStrategy,
    OutputType,
    SectionOutput,
)


class ValidationIssueSeverity(str, Enum):
    """
    Severity for validation issues.
    """

    ERROR = "error"
    WARNING = "warning"


class ValidationIssueCode(str, Enum):
    """
    Typed validation issue codes for downstream retry/debug handling.
    """

    STRATEGY_OUTPUT_MISMATCH = "strategy_output_mismatch"
    EMPTY_OUTPUT = "empty_output"
    MARKDOWN_INLINE_HTML_NOT_ALLOWED = "markdown_inline_html_not_allowed"
    MARKDOWN_NESTED_LIST_NOT_ALLOWED = "markdown_nested_list_not_allowed"
    MARKDOWN_UNSUPPORTED_HEADING = "markdown_unsupported_heading"
    MARKDOWN_UNBALANCED_CODE_FENCE = "markdown_unbalanced_code_fence"
    TABLE_REQUIRED_COLUMNS_MISSING = "table_required_columns_missing"
    TABLE_MIN_ROWS_NOT_MET = "table_min_rows_not_met"
    TABLE_MARKDOWN_NOT_FOUND = "table_markdown_not_found"
    TEXT_MIN_WORDS_NOT_MET = "text_min_words_not_met"
    TEXT_MAX_WORDS_EXCEEDED = "text_max_words_exceeded"
    BANNED_PHRASE_FOUND = "banned_phrase_found"
    LOW_EVIDENCE_PREFIX_MISSING = "low_evidence_prefix_missing"
    DIAGRAM_ARTIFACT_MISSING = "diagram_artifact_missing"


class ValidationIssue(BaseModel):
    """
    One validation issue.
    """

    model_config = ConfigDict(extra="forbid")

    code: ValidationIssueCode = Field(description="Typed validation issue code.")
    severity: ValidationIssueSeverity = Field(
        default=ValidationIssueSeverity.ERROR,
        description="Severity of the validation issue.",
    )
    message: str = Field(description="Human-readable validation detail.")
    line_number: int | None = Field(
        default=None,
        ge=1,
        description="Optional source line number when relevant.",
    )


class OutputValidationRules(BaseModel):
    """
    Validation rules for one generated section output.

    These are Generation-consumed validation rules and can be populated
    from Template-resolved section metadata without redefining Template contracts here.
    """

    model_config = ConfigDict(extra="forbid")

    min_words: int | None = Field(default=None, ge=0)
    max_words: int | None = Field(default=None, ge=0)
    required_columns: list[str] = Field(default_factory=list)
    min_rows: int | None = Field(default=None, ge=0)
    banned_phrases: list[str] = Field(default_factory=list)
    require_low_evidence_prefix: bool = Field(
        default=False,
        description="Require [LOW EVIDENCE] prefix for degraded/low-evidence outputs.",
    )


class OutputValidationRequest(BaseModel):
    """
    Input payload for validating one generated section output.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="Stable section identifier.")
    section_heading: str | None = Field(default=None, description="Section heading/title.")
    strategy: GenerationStrategy = Field(description="Resolved Generation strategy.")
    output: SectionOutput = Field(description="Generated output payload to validate.")
    rules: OutputValidationRules = Field(
        default_factory=OutputValidationRules,
        description="Section-level validation rules.",
    )
    low_evidence: bool = Field(
        default=False,
        description="Whether the section is already marked as low-evidence/degraded.",
    )


class OutputValidationResult(BaseModel):
    """
    Final validation result for one generated section output.
    """

    model_config = ConfigDict(extra="forbid")

    is_valid: bool = Field(description="True when no ERROR issues are present.")
    issues: list[ValidationIssue] = Field(default_factory=list)
    normalized_output: SectionOutput = Field(
        description="Normalized output payload after validation-safe cleanup."
    )
    word_count: int = Field(default=0, ge=0)
    table_row_count: int | None = Field(default=None, ge=0)


class OutputValidator:
    """
    Validates generated section outputs against:
    - Generation strategy/output contract
    - markdown contract
    - section-level rules
    """

    _INLINE_HTML_RE = re.compile(r"<[^>]+>")
    _NESTED_LIST_RE = re.compile(r"^\s{2,}([-*+]|\d+\.)\s+")
    _HEADING_RE = re.compile(r"^(#+)\s+")
    _TABLE_ROW_RE = re.compile(r"^\|.*\|$")
    _WORD_RE = re.compile(r"\b\w+\b")

    def validate(self, request: OutputValidationRequest) -> OutputValidationResult:
        issues: list[ValidationIssue] = []

        normalized_output = self._normalize_output(request.output)

        # ------------------------------------------------------------------
        # Strategy <-> output type alignment
        # ------------------------------------------------------------------
        expected_output_type = self._expected_output_type_for_strategy(request.strategy)
        if normalized_output.output_type != expected_output_type:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.STRATEGY_OUTPUT_MISMATCH,
                    message=(
                        f"Strategy '{request.strategy.value}' requires output type "
                        f"'{expected_output_type.value}', got '{normalized_output.output_type.value}'."
                    ),
                )
            )

        # ------------------------------------------------------------------
        # Type-specific validation
        # ------------------------------------------------------------------
        word_count = 0
        table_row_count: int | None = None

        if normalized_output.output_type in {
            OutputType.MARKDOWN_TEXT,
            OutputType.MARKDOWN_TABLE,
        }:
            content = normalized_output.content_markdown or ""

            if not content.strip():
                issues.append(
                    ValidationIssue(
                        code=ValidationIssueCode.EMPTY_OUTPUT,
                        message="Generated markdown output is empty.",
                    )
                )
            else:
                markdown_issues = self._validate_markdown_contract(content)
                issues.extend(markdown_issues)

                word_count = self._count_words(content)

                # low-evidence prefix check when requested
                if request.rules.require_low_evidence_prefix or request.low_evidence:
                    if not content.lstrip().startswith("[LOW EVIDENCE]"):
                        issues.append(
                            ValidationIssue(
                                code=ValidationIssueCode.LOW_EVIDENCE_PREFIX_MISSING,
                                message="Low-evidence output must start with '[LOW EVIDENCE]'.",
                            )
                        )

                # banned phrases
                issues.extend(self._validate_banned_phrases(content, request.rules.banned_phrases))

                # word-count rules
                if request.rules.min_words is not None and word_count < request.rules.min_words:
                    issues.append(
                        ValidationIssue(
                            code=ValidationIssueCode.TEXT_MIN_WORDS_NOT_MET,
                            message=(
                                f"Word count {word_count} is below min_words={request.rules.min_words}."
                            ),
                        )
                    )

                if request.rules.max_words is not None and word_count > request.rules.max_words:
                    issues.append(
                        ValidationIssue(
                            code=ValidationIssueCode.TEXT_MAX_WORDS_EXCEEDED,
                            message=(
                                f"Word count {word_count} exceeds max_words={request.rules.max_words}."
                            ),
                        )
                    )

                # table-specific rules
                if normalized_output.output_type == OutputType.MARKDOWN_TABLE:
                    table_row_count, table_issues = self._validate_markdown_table(
                        content=content,
                        required_columns=request.rules.required_columns,
                        min_rows=request.rules.min_rows,
                    )
                    issues.extend(table_issues)

        elif normalized_output.output_type == OutputType.DIAGRAM_ARTIFACT:
            diagram_artifacts = normalized_output.diagram_artifacts

            if diagram_artifacts is None:
                issues.append(
                    ValidationIssue(
                        code=ValidationIssueCode.DIAGRAM_ARTIFACT_MISSING,
                        message="Diagram output is missing diagram_artifacts payload.",
                    )
                )
            else:
                if not (
                    diagram_artifacts.puml_path
                    or diagram_artifacts.png_path
                    or diagram_artifacts.svg_path
                ):
                    issues.append(
                        ValidationIssue(
                            code=ValidationIssueCode.DIAGRAM_ARTIFACT_MISSING,
                            message=(
                                "Diagram output must include at least one artifact reference "
                                "(puml_path, png_path, or svg_path)."
                            ),
                        )
                    )

        is_valid = not any(issue.severity == ValidationIssueSeverity.ERROR for issue in issues)

        return OutputValidationResult(
            is_valid=is_valid,
            issues=issues,
            normalized_output=normalized_output,
            word_count=word_count,
            table_row_count=table_row_count,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _expected_output_type_for_strategy(
        self,
        strategy: GenerationStrategy,
    ) -> OutputType:
        if strategy == GenerationStrategy.SUMMARIZE_TEXT:
            return OutputType.MARKDOWN_TEXT
        if strategy == GenerationStrategy.GENERATE_TABLE:
            return OutputType.MARKDOWN_TABLE
        return OutputType.DIAGRAM_ARTIFACT

    def _normalize_output(self, output: SectionOutput) -> SectionOutput:
        """
        Normalize markdown outputs by trimming surrounding whitespace.

        Diagram outputs are returned as-is.
        """
        if output.output_type in {OutputType.MARKDOWN_TEXT, OutputType.MARKDOWN_TABLE}:
            normalized_text = (output.content_markdown or "").strip()
            return SectionOutput(
                output_type=output.output_type,
                content_markdown=normalized_text,
                diagram_artifacts=None,
                metadata=output.metadata,
            )

        return output

    def _validate_markdown_contract(self, content: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        lines = content.splitlines()

        # Inline HTML is not allowed.
        if self._INLINE_HTML_RE.search(content):
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.MARKDOWN_INLINE_HTML_NOT_ALLOWED,
                    message="Inline HTML is not allowed in Generation markdown output.",
                )
            )

        # Code fences must be balanced.
        fence_count = sum(1 for line in lines if line.strip().startswith("```"))
        if fence_count % 2 != 0:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.MARKDOWN_UNBALANCED_CODE_FENCE,
                    message="Markdown code fences are unbalanced.",
                )
            )

        for idx, line in enumerate(lines, start=1):
            stripped = line.rstrip()

            if not stripped:
                continue

            # Nested lists are not allowed.
            if self._NESTED_LIST_RE.match(line):
                issues.append(
                    ValidationIssue(
                        code=ValidationIssueCode.MARKDOWN_NESTED_LIST_NOT_ALLOWED,
                        message="Nested markdown lists are not supported.",
                        line_number=idx,
                    )
                )

            # Only ## and ### headings are allowed.
            heading_match = self._HEADING_RE.match(stripped)
            if heading_match:
                heading_marks = heading_match.group(1)
                if heading_marks not in {"##", "###"}:
                    issues.append(
                        ValidationIssue(
                            code=ValidationIssueCode.MARKDOWN_UNSUPPORTED_HEADING,
                            message="Only ## and ### headings are allowed.",
                            line_number=idx,
                        )
                    )

        return issues

    def _validate_banned_phrases(
        self,
        content: str,
        banned_phrases: list[str],
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        lowered_content = content.lower()

        for phrase in banned_phrases:
            if phrase and phrase.lower() in lowered_content:
                issues.append(
                    ValidationIssue(
                        code=ValidationIssueCode.BANNED_PHRASE_FOUND,
                        message=f"Banned phrase found: '{phrase}'.",
                    )
                )

        return issues

    def _count_words(self, content: str) -> int:
        """
        Count words with a simple regex after stripping basic markdown fence symbols.
        """
        return len(self._WORD_RE.findall(content))

    def _validate_markdown_table(
        self,
        content: str,
        required_columns: list[str],
        min_rows: int | None,
    ) -> tuple[int | None, list[ValidationIssue]]:
        issues: list[ValidationIssue] = []

        table_lines = [line.strip() for line in content.splitlines() if self._TABLE_ROW_RE.match(line.strip())]

        if len(table_lines) < 2:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.TABLE_MARKDOWN_NOT_FOUND,
                    message="Markdown table header/separator not found.",
                )
            )
            return None, issues

        header_cells = self._split_markdown_row(table_lines[0])

        if required_columns:
            missing_columns = [col for col in required_columns if col not in header_cells]
            if missing_columns:
                issues.append(
                    ValidationIssue(
                        code=ValidationIssueCode.TABLE_REQUIRED_COLUMNS_MISSING,
                        message=(
                            "Required table columns are missing: "
                            + ", ".join(missing_columns)
                        ),
                    )
                )

        # Row count excludes header + separator line
        data_rows = table_lines[2:] if len(table_lines) >= 3 else []
        row_count = len(data_rows)

        if min_rows is not None and row_count < min_rows:
            issues.append(
                ValidationIssue(
                    code=ValidationIssueCode.TABLE_MIN_ROWS_NOT_MET,
                    message=f"Table row count {row_count} is below min_rows={min_rows}.",
                )
            )

        return row_count, issues

    def _split_markdown_row(self, row: str) -> list[str]:
        """
        Split a markdown table row into normalized cell names.
        """
        stripped = row.strip().strip("|")
        return [cell.strip() for cell in stripped.split("|")]