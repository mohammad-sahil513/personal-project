"""
Validation result contracts for the Template module.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, computed_field

from ..models.template_enums import TemplateValidationCode, ValidationSeverity


class TemplateValidationIssue(BaseModel):
    """A typed validation issue produced by the template validator."""

    model_config = ConfigDict(extra="forbid")

    code: TemplateValidationCode
    severity: ValidationSeverity
    message: str = Field(..., min_length=1)
    field_path: str | None = Field(
        default=None,
        description="Optional dotted path to the offending field.",
    )
    context: dict[str, str] = Field(
        default_factory=dict,
        description="Optional lightweight context for debugging or UI display.",
    )


class TemplateValidationResult(BaseModel):
    """
    Aggregated validation result for a template artifact.

    Computed properties make it convenient for services/tests to inspect
    validity without duplicating filtering logic.
    """

    model_config = ConfigDict(extra="forbid")

    issues: list[TemplateValidationIssue] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def error_count(self) -> int:
        """Number of error-severity issues."""
        return sum(issue.severity == ValidationSeverity.ERROR for issue in self.issues)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def warning_count(self) -> int:
        """Number of warning-severity issues."""
        return sum(issue.severity == ValidationSeverity.WARNING for issue in self.issues)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_valid(self) -> bool:
        """A template is valid when no error-severity issues are present."""
        return self.error_count == 0

    def add_issue(self, issue: TemplateValidationIssue) -> None:
        """Append a typed validation issue."""
        self.issues.append(issue)

    def add_error(
        self,
        *,
        code: TemplateValidationCode,
        message: str,
        field_path: str | None = None,
        context: dict[str, str] | None = None,
    ) -> None:
        """Convenience helper for adding an error issue."""
        self.issues.append(
            TemplateValidationIssue(
                code=code,
                severity=ValidationSeverity.ERROR,
                message=message,
                field_path=field_path,
                context=context or {},
            )
        )

    def add_warning(
        self,
        *,
        code: TemplateValidationCode,
        message: str,
        field_path: str | None = None,
        context: dict[str, str] | None = None,
    ) -> None:
        """Convenience helper for adding a warning issue."""
        self.issues.append(
            TemplateValidationIssue(
                code=code,
                severity=ValidationSeverity.WARNING,
                message=message,
                field_path=field_path,
                context=context or {},
            )
        )