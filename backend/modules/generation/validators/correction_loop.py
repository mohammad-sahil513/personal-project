"""
Correction loop for the Generation module.

Responsibilities:
- Retry only after validation failure
- Use a bounded number of retries
- Build a correction prompt from:
    - the original assembled prompt
    - the invalid generated output
    - the validation issues
- Return the first corrected output that passes validation

Important:
- This file does NOT handle initial generation.
- This file does NOT handle diagram repair; diagram repair belongs to diagram/repair_loop.py.
- This file must not change section identity.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.generation.contracts.generation_contracts import (
    GenerationStrategy,
    OutputType,
    SectionOutput,
)
from backend.modules.generation.models.generation_config import (
    DEFAULT_GENERATION_CONFIG,
    GenerationConfig,
)
from backend.modules.generation.validators.output_validator import (
    OutputValidationRequest,
    OutputValidationResult,
    OutputValidationRules,
    OutputValidator,
)


@runtime_checkable
class CorrectionBackend(Protocol):
    """
    Protocol for an injected correction backend.

    This keeps the correction loop decoupled from the concrete Semantic Kernel
    implementation while preserving a stable contract for production wiring.
    """

    def correct_output(
        self,
        prompt: str,
        *,
        model_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | dict[str, Any]:
        """
        Correct a previously generated invalid output.

        Returns either:
        - a plain string containing corrected markdown content, or
        - a mapping that includes at least a `text` field and optionally metadata
        """
        ...


class CorrectionAttemptRecord(BaseModel):
    """
    One correction attempt with validation result and backend metadata.
    """

    model_config = ConfigDict(extra="forbid")

    attempt_number: int = Field(ge=1, description="1-based retry attempt number.")
    corrected_output: SectionOutput = Field(
        description="Corrected output candidate returned by the backend."
    )
    validation_result: OutputValidationResult = Field(
        description="Validation result for this corrected output candidate."
    )
    backend_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional backend metadata for the attempt.",
    )


class CorrectionLoopRequest(BaseModel):
    """
    Input payload for the correction loop.

    The correction loop only runs after an initial validation failure.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="Stable section identifier.")
    section_heading: str = Field(description="Section heading/title.")
    strategy: GenerationStrategy = Field(description="Resolved Generation strategy.")
    original_prompt_text: str = Field(description="Original assembled prompt.")
    initial_output: SectionOutput = Field(description="Invalid generated output to repair.")
    initial_validation_result: OutputValidationResult = Field(
        description="Validation result from the invalid initial output."
    )
    validation_rules: OutputValidationRules = Field(
        default_factory=OutputValidationRules,
        description="Section-level validation rules reused for correction validation.",
    )
    low_evidence: bool = Field(
        default=False,
        description="Whether the section is marked as low-evidence/degraded.",
    )
    model_name: str | None = Field(
        default=None,
        description="Optional correction backend/deployment/model name hint.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata passed through to the correction backend.",
    )
    max_retries: int | None = Field(
        default=None,
        ge=0,
        description="Optional override for correction retry count.",
    )

    @field_validator("original_prompt_text")
    @classmethod
    def validate_original_prompt_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("original_prompt_text cannot be empty.")
        return value

    @field_validator("initial_validation_result")
    @classmethod
    def validate_initial_failure(cls, value: OutputValidationResult) -> OutputValidationResult:
        """
        Correction loop may only start after an actual validation failure.
        """
        if value.is_valid:
            raise ValueError(
                "Correction loop should only be invoked when initial validation has failed."
            )
        return value


class CorrectionLoopResult(BaseModel):
    """
    Final result of the bounded correction loop.
    """

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(description="True when a corrected output passed validation.")
    final_output: SectionOutput = Field(
        description="The final chosen output (corrected or original invalid output)."
    )
    final_validation_result: OutputValidationResult = Field(
        description="Validation result corresponding to final_output."
    )
    attempts_used: int = Field(ge=0, description="Number of correction attempts actually used.")
    max_retries: int = Field(ge=0, description="Maximum allowed retries for this loop.")
    attempt_history: list[CorrectionAttemptRecord] = Field(
        default_factory=list,
        description="Ordered history of correction attempts.",
    )
    last_backend_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Backend metadata from the final attempt, if any.",
    )


class CorrectionLoop:
    """
    Bounded correction loop for text/table Generation outputs.

    Diagram-specific repair is intentionally excluded and handled in the
    diagram runtime path.
    """

    def __init__(
        self,
        validator: OutputValidator,
        backend: CorrectionBackend,
        config: GenerationConfig | None = None,
    ) -> None:
        if not isinstance(backend, CorrectionBackend):
            raise TypeError("backend must implement the CorrectionBackend protocol.")

        self.validator = validator
        self.backend = backend
        self.config = config or DEFAULT_GENERATION_CONFIG

    def retry(self, request: CorrectionLoopRequest) -> CorrectionLoopResult:
        """
        Attempt bounded correction retries until:
        - output becomes valid, or
        - max retries are exhausted.

        Rules:
        - retry only after failed validation
        - preserve section identity
        - do not handle diagram correction here
        """
        if request.strategy == GenerationStrategy.DIAGRAM_PLANTUML:
            raise ValueError(
                "Diagram correction is not handled by correction_loop.py. "
                "Use the diagram runtime repair loop instead."
            )

        max_retries = (
            request.max_retries
            if request.max_retries is not None
            else self.config.max_retries
        )

        final_output = request.initial_output
        final_validation_result = request.initial_validation_result
        attempt_history: list[CorrectionAttemptRecord] = []
        last_backend_metadata: dict[str, Any] = {}

        for attempt_number in range(1, max_retries + 1):
            correction_prompt = self._build_correction_prompt(
                section_id=request.section_id,
                section_heading=request.section_heading,
                strategy=request.strategy,
                original_prompt_text=request.original_prompt_text,
                invalid_output=final_output,
                validation_result=final_validation_result,
            )

            backend_result = self.backend.correct_output(
                correction_prompt,
                model_name=request.model_name,
                metadata=request.metadata,
            )

            corrected_text, backend_metadata = self._coerce_backend_result(backend_result)
            normalized_text = self._normalize_markdown_output(corrected_text)
            last_backend_metadata = backend_metadata

            corrected_output = SectionOutput(
                output_type=self._expected_output_type_for_strategy(request.strategy),
                content_markdown=normalized_text,
                metadata={
                    **request.initial_output.metadata,
                    "correction_attempt": attempt_number,
                },
            )

            validation_result = self.validator.validate(
                OutputValidationRequest(
                    section_id=request.section_id,
                    section_heading=request.section_heading,
                    strategy=request.strategy,
                    output=corrected_output,
                    rules=request.validation_rules,
                    low_evidence=request.low_evidence,
                )
            )

            attempt_record = CorrectionAttemptRecord(
                attempt_number=attempt_number,
                corrected_output=corrected_output,
                validation_result=validation_result,
                backend_metadata=backend_metadata,
            )
            attempt_history.append(attempt_record)

            final_output = corrected_output
            final_validation_result = validation_result

            if validation_result.is_valid:
                return CorrectionLoopResult(
                    success=True,
                    final_output=final_output,
                    final_validation_result=final_validation_result,
                    attempts_used=attempt_number,
                    max_retries=max_retries,
                    attempt_history=attempt_history,
                    last_backend_metadata=last_backend_metadata,
                )

        return CorrectionLoopResult(
            success=False,
            final_output=final_output,
            final_validation_result=final_validation_result,
            attempts_used=len(attempt_history),
            max_retries=max_retries,
            attempt_history=attempt_history,
            last_backend_metadata=last_backend_metadata,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_correction_prompt(
        self,
        *,
        section_id: str,
        section_heading: str,
        strategy: GenerationStrategy,
        original_prompt_text: str,
        invalid_output: SectionOutput,
        validation_result: OutputValidationResult,
    ) -> str:
        """
        Build a targeted correction prompt without changing section identity.
        """
        issues_text = "\n".join(
            f"- [{issue.code.value}] {issue.message}"
            for issue in validation_result.issues
        ).strip()

        current_output_text = invalid_output.content_markdown or ""

        return (
            "# CORRECTION TASK\n"
            "You are repairing a generated section output that failed validation.\n\n"
            "# DO NOT CHANGE IDENTITY\n"
            f"Section ID: {section_id}\n"
            f"Section Heading: {section_heading}\n"
            f"Strategy: {strategy.value}\n\n"
            "# ORIGINAL PROMPT\n"
            f"{original_prompt_text}\n\n"
            "# INVALID OUTPUT\n"
            f"{current_output_text}\n\n"
            "# VALIDATION ISSUES TO FIX\n"
            f"{issues_text}\n\n"
            "# REQUIREMENTS\n"
            "- Preserve the same section identity and intent.\n"
            "- Fix only the validation issues.\n"
            "- Return only corrected markdown content.\n"
            "- Do not add explanations.\n"
        ).strip()

    def _coerce_backend_result(
        self,
        backend_result: str | dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """
        Normalize backend output into `(text, metadata)`.

        Supported backend return shapes:
        - plain string
        - mapping with at least `text`
        """
        if isinstance(backend_result, str):
            return backend_result, {}

        if isinstance(backend_result, dict):
            text = backend_result.get("text")
            if not isinstance(text, str):
                raise ValueError(
                    "Backend dictionary response must include a string `text` field."
                )

            metadata = {
                key: value
                for key, value in backend_result.items()
                if key != "text"
            }
            return text, metadata

        raise TypeError(
            "Unsupported backend result type. Expected `str` or `dict[str, Any]`."
        )

    def _normalize_markdown_output(self, text: str) -> str:
        """
        Normalize corrected markdown output.

        Practical cleanup:
        - trim whitespace
        - unwrap fenced markdown blocks
        """
        normalized = text.strip()

        if normalized.startswith("```") and normalized.endswith("```"):
            lines = normalized.splitlines()
            if len(lines) >= 2:
                normalized = "\n".join(lines[1:-1]).strip()

        return normalized

    def _expected_output_type_for_strategy(
        self,
        strategy: GenerationStrategy,
    ) -> OutputType:
        if strategy == GenerationStrategy.SUMMARIZE_TEXT:
            return OutputType.MARKDOWN_TEXT
        if strategy == GenerationStrategy.GENERATE_TABLE:
            return OutputType.MARKDOWN_TABLE
        return OutputType.DIAGRAM_ARTIFACT