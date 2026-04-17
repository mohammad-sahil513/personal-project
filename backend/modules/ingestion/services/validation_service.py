"""
Validation service for Stage 7.

This service performs deterministic validation across:
- parse quality
- section integrity
- asset consistency
- optional PII verification
- pre-chunking readiness

Validation outcome rules:
- any ERROR issue means global failure for downstream progression
- WARNING issues allow the pipeline to continue
"""

from __future__ import annotations

import re
from collections import Counter
from time import perf_counter

from backend.modules.ingestion.contracts.stage_1_contracts import StageWarning
from backend.modules.ingestion.contracts.stage_7_contracts import (
    Stage7Input,
    Stage7Metrics,
    Stage7Output,
    ValidationIssue,
    ValidationIssueCode,
    ValidationSeverity,
    ValidationSummary,
)


class ValidationService:
    """Service that executes deterministic Stage 7 validation rules."""

    _ASSET_PLACEHOLDER_PATTERN = re.compile(r"!\[[^\]]*\]\([^)]+\)|<img\b[^>]*>", re.IGNORECASE)
    _VISION_BLOCK_PATTERN = re.compile(r"\[VISION_EXTRACTED:(?P<body>.*?)\]", re.DOTALL)
    _EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    _PHONE_PATTERN = re.compile(r"\b(?:\+?\d[\d\s\-()]{7,}\d)\b")

    def validate(self, request: Stage7Input) -> Stage7Output:
        """Run all Stage 7 validators and return an aggregated validation output."""
        start_time = perf_counter()
        issues: list[ValidationIssue] = []

        issues.extend(self._validate_parse_quality(request))
        issues.extend(self._validate_section_integrity(request))
        issues.extend(self._validate_asset_and_vision_consistency(request))
        issues.extend(self._validate_pii_verification(request))
        issues.extend(self._validate_pre_chunking_readiness(request))

        error_count = sum(1 for issue in issues if issue.severity == ValidationSeverity.ERROR)
        warning_count = sum(1 for issue in issues if issue.severity == ValidationSeverity.WARNING)

        warnings = [self._to_stage_warning(issue) for issue in issues if issue.severity == ValidationSeverity.WARNING]

        summary = ValidationSummary(
            total_issues=len(issues),
            error_count=error_count,
            warning_count=warning_count,
            has_global_failure=error_count > 0,
            can_proceed_to_chunking=error_count == 0,
        )

        total_duration_ms = (perf_counter() - start_time) * 1000
        metrics = Stage7Metrics(
            total_sections_checked=len(request.sections),
            total_assets_checked=len(request.asset_registry.assets),
            total_duration_ms=round(total_duration_ms, 3),
        )

        return Stage7Output(
            process_id=request.process_id,
            document_id=request.document_id,
            source_blob=request.source_blob,
            sections=request.sections,
            issues=issues,
            summary=summary,
            warnings=[*request.prior_warnings, *warnings],
            metrics=metrics,
        )

    def _validate_parse_quality(self, request: Stage7Input) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        report = request.parse_quality_report

        if report.estimated_tokens <= 0:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code=ValidationIssueCode.EMPTY_MARKDOWN,
                    message="Parsed markdown appears to be empty or tokenless.",
                    details={"estimated_tokens": report.estimated_tokens},
                )
            )

        if report.heading_count <= 0:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code=ValidationIssueCode.MISSING_HEADINGS,
                    message="No headings were found in the parsed markdown.",
                    details={"heading_count": report.heading_count},
                )
            )

        if report.estimated_tokens > 1_000_000:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code=ValidationIssueCode.TOKEN_SANITY_OUT_OF_BOUNDS,
                    message="Estimated token count is outside sane bounds for a single document.",
                    details={"estimated_tokens": report.estimated_tokens},
                )
            )

        return issues

    def _validate_section_integrity(self, request: Stage7Input) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        if not request.sections:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code=ValidationIssueCode.NO_SECTIONS_FOUND,
                    message="No sections were available after deterministic segmentation.",
                    details={},
                )
            )
            return issues

        section_id_counts = Counter(section.section_id for section in request.sections)
        duplicate_section_ids = [section_id for section_id, count in section_id_counts.items() if count > 1]

        for duplicate_section_id in duplicate_section_ids:
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code=ValidationIssueCode.DUPLICATE_SECTION_ID,
                    message="Duplicate section_id detected.",
                    section_id=duplicate_section_id,
                    details={"section_id": duplicate_section_id},
                )
            )

        for section in request.sections:
            if not section.raw_content.strip():
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code=ValidationIssueCode.EMPTY_SECTION_CONTENT,
                        message="Section content is empty after cleanup and segmentation.",
                        section_id=section.section_id,
                        details={"heading": section.heading},
                    )
                )

        return issues

    def _validate_asset_and_vision_consistency(self, request: Stage7Input) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        section_content = "\n\n".join(section.raw_content for section in request.sections)

        discovered_placeholders = {
            match.group(0) for match in self._ASSET_PLACEHOLDER_PATTERN.finditer(section_content)
        }
        registered_placeholders = {asset.placeholder for asset in request.asset_registry.assets}

        for placeholder in sorted(discovered_placeholders - registered_placeholders):
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    code=ValidationIssueCode.UNRESOLVED_ASSET_PLACEHOLDER,
                    message="An asset placeholder exists in content but does not resolve in the asset registry.",
                    details={"placeholder": placeholder},
                )
            )

        for placeholder in sorted(registered_placeholders - discovered_placeholders):
            issues.append(
                ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    code=ValidationIssueCode.UNREFERENCED_ASSET_REGISTRY_ENTRY,
                    message="An asset registry entry was created but is not referenced in segmented content.",
                    details={"placeholder": placeholder},
                )
            )

        for match in self._VISION_BLOCK_PATTERN.finditer(section_content):
            if not match.group("body").strip():
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code=ValidationIssueCode.EMPTY_VISION_BLOCK,
                        message="A [VISION_EXTRACTED: ...] block was present but empty.",
                        details={},
                    )
                )

        return issues

    def _validate_pii_verification(self, request: Stage7Input) -> list[ValidationIssue]:
        if not request.pii_enabled:
            return []

        issues: list[ValidationIssue] = []
        section_content = "\n\n".join(section.raw_content for section in request.sections)

        normalized_allowlist = {email.strip().lower() for email in request.allowlisted_system_emails}
        normalized_mapped_values = {value.strip().lower() for value in request.mapped_pii_values}

        for match in self._EMAIL_PATTERN.finditer(section_content):
            email = match.group(0).strip().lower()

            if email in normalized_allowlist:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        code=ValidationIssueCode.POSSIBLE_PII_LEAK_EXCLUDING_SYSTEM_IDENTIFIER,
                        message="A regex-matched email was ignored because it is allowlisted as a system/service email.",
                        details={"value": email},
                    )
                )
                continue

            if email not in normalized_mapped_values:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code=ValidationIssueCode.POSSIBLE_PII_LEAK,
                        message="A possible personal email leak was detected that is not explained by the secure mapping.",
                        details={"value": email},
                    )
                )

        for match in self._PHONE_PATTERN.finditer(section_content):
            phone_value = match.group(0).strip().lower()
            if phone_value not in normalized_mapped_values:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        code=ValidationIssueCode.POSSIBLE_PII_LEAK,
                        message="A possible phone-number leak was detected that is not explained by the secure mapping.",
                        details={"value": phone_value},
                    )
                )

        return issues

    def _validate_pre_chunking_readiness(self, request: Stage7Input) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        for section in request.sections:
            if section.structural_signals.estimated_tokens > 15_000:
                issues.append(
                    ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        code=ValidationIssueCode.OVERSIZED_SECTION_WARNING,
                        message="Section token estimate exceeds the recommended pre-chunking threshold.",
                        section_id=section.section_id,
                        details={"estimated_tokens": section.structural_signals.estimated_tokens},
                    )
                )

        return issues

    @staticmethod
    def _to_stage_warning(issue: ValidationIssue) -> StageWarning:
        """Convert a warning-level validation issue into the generic stage-warning format."""
        return StageWarning(
            code=issue.code.value,
            message=issue.message,
            details={
                "section_id": issue.section_id,
                **issue.details,
            },
        )