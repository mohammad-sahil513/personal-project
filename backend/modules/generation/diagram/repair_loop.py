"""
Diagram repair loop for the Generation module.

Responsibilities:
- Retry only after diagram render failure
- Use a bounded number of repair attempts
- Produce repaired PlantUML candidates through an injected backend
- Normalize, validate, and re-render each repaired candidate
- Return the first repaired PlantUML source that successfully renders

Important:
- This file is diagram-specific repair logic only.
- It does NOT replace the generic text/table correction loop.
- It does NOT persist artifacts or embed diagrams.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ------------------------------------------------------------------------------
# Protocols
# ------------------------------------------------------------------------------


@runtime_checkable
class DiagramRepairBackend(Protocol):
    """
    Backend that produces repaired PlantUML text from a failed diagram attempt.
    """

    def repair_puml(
        self,
        prompt: str,
        *,
        model_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | dict[str, Any]:
        """
        Returns either:
        - repaired PlantUML source as a string
        - or a mapping with at least a `text` field and optional metadata
        """
        ...


@runtime_checkable
class PlantUMLNormalizerProtocol(Protocol):
    """
    Normalizes repaired PlantUML text.
    """

    def normalize(self, puml_text: str) -> str:
        ...


@runtime_checkable
class PlantUMLValidatorProtocol(Protocol):
    """
    Validates normalized PlantUML text.
    """

    def validate(self, puml_text: str) -> tuple[bool, list[str]]:
        ...


@runtime_checkable
class DiagramRendererProtocol(Protocol):
    """
    Renders PlantUML text to concrete artifacts.
    """

    def render(self, puml_text: str) -> dict[str, Any]:
        """
        Expected keys:
        - success: bool
        - svg_content: str | bytes | None
        - png_content: bytes | None
        - error_message: str | None
        """
        ...


# ------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------


class DiagramRepairRequest(BaseModel):
    """
    Input payload for the bounded diagram repair loop.
    """

    model_config = ConfigDict(extra="forbid")

    original_prompt_text: str = Field(
        description="Original diagram-generation prompt."
    )
    current_puml_text: str = Field(
        description="Current normalized PlantUML source that failed to render."
    )
    render_error: str | None = Field(
        default=None,
        description="Renderer/Kroki failure detail from the last render attempt.",
    )
    model_name: str | None = Field(
        default=None,
        description="Optional repair backend/deployment/model name hint.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata passed through the repair path.",
    )

    @field_validator("original_prompt_text", "current_puml_text")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Repair-loop text inputs cannot be empty.")
        return value


class DiagramRepairAttemptRecord(BaseModel):
    """
    One repair attempt with validation/render outcomes.
    """

    model_config = ConfigDict(extra="forbid")

    attempt_number: int = Field(ge=1)
    repaired_puml_text: str = Field(description="Normalized repaired PlantUML candidate.")
    validation_issues: list[str] = Field(default_factory=list)
    render_success: bool = Field(description="Whether the repaired candidate rendered successfully.")
    render_error: str | None = Field(default=None)
    backend_metadata: dict[str, Any] = Field(default_factory=dict)


class DiagramRepairResult(BaseModel):
    """
    Final result of the bounded diagram repair loop.
    """

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(description="True when a repaired candidate rendered successfully.")
    repaired_puml_text: str | None = Field(
        default=None,
        description="The first repaired PlantUML source that passed validation and render.",
    )
    attempts_used: int = Field(ge=0)
    attempt_history: list[DiagramRepairAttemptRecord] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Aggregated metadata from the repair loop.",
    )


# ------------------------------------------------------------------------------
# Service
# ------------------------------------------------------------------------------


class DiagramRepairLoopService:
    """
    Bounded repair loop for diagram render failures.
    """

    def __init__(
        self,
        backend: DiagramRepairBackend,
        normalizer: PlantUMLNormalizerProtocol,
        validator: PlantUMLValidatorProtocol,
        renderer: DiagramRendererProtocol,
        *,
        max_retries: int = 2,
    ) -> None:
        if not isinstance(backend, DiagramRepairBackend):
            raise TypeError("backend must implement DiagramRepairBackend.")
        if not isinstance(normalizer, PlantUMLNormalizerProtocol):
            raise TypeError("normalizer must implement PlantUMLNormalizerProtocol.")
        if not isinstance(validator, PlantUMLValidatorProtocol):
            raise TypeError("validator must implement PlantUMLValidatorProtocol.")
        if not isinstance(renderer, DiagramRendererProtocol):
            raise TypeError("renderer must implement DiagramRendererProtocol.")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative.")

        self.backend = backend
        self.normalizer = normalizer
        self.validator = validator
        self.renderer = renderer
        self.max_retries = max_retries

    def repair(
        self,
        *,
        original_prompt_text: str,
        current_puml_text: str,
        render_error: str | None,
        model_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Attempt bounded PlantUML repair until:
        - a repaired candidate validates and renders successfully, or
        - max retries are exhausted

        Returned shape is intentionally compatible with DiagramGenerator.
        """
        request = DiagramRepairRequest(
            original_prompt_text=original_prompt_text,
            current_puml_text=current_puml_text,
            render_error=render_error,
            model_name=model_name,
            metadata=metadata or {},
        )

        attempt_history: list[DiagramRepairAttemptRecord] = []
        last_backend_metadata: dict[str, Any] = {}
        current_failed_puml = request.current_puml_text
        current_render_error = request.render_error

        for attempt_number in range(1, self.max_retries + 1):
            repair_prompt = self._build_repair_prompt(
                original_prompt_text=request.original_prompt_text,
                current_puml_text=current_failed_puml,
                render_error=current_render_error,
            )

            backend_result = self.backend.repair_puml(
                repair_prompt,
                model_name=request.model_name,
                metadata=request.metadata,
            )

            repaired_raw_text, backend_metadata = self._coerce_backend_result(backend_result)
            last_backend_metadata = backend_metadata

            if not repaired_raw_text.strip():
                attempt_history.append(
                    DiagramRepairAttemptRecord(
                        attempt_number=attempt_number,
                        repaired_puml_text="",
                        validation_issues=["Repair backend returned empty PlantUML text."],
                        render_success=False,
                        render_error="Empty repaired PlantUML text.",
                        backend_metadata=backend_metadata,
                    )
                )
                current_render_error = "Empty repaired PlantUML text."
                continue

            normalized_text = self.normalizer.normalize(repaired_raw_text)
            is_valid, validation_issues = self.validator.validate(normalized_text)

            if not is_valid:
                attempt_history.append(
                    DiagramRepairAttemptRecord(
                        attempt_number=attempt_number,
                        repaired_puml_text=normalized_text,
                        validation_issues=validation_issues,
                        render_success=False,
                        render_error="PlantUML validation failed after repair.",
                        backend_metadata=backend_metadata,
                    )
                )
                current_failed_puml = normalized_text
                current_render_error = "PlantUML validation failed after repair."
                continue

            render_result = self.renderer.render(normalized_text)
            render_success = bool(render_result.get("success"))
            render_failure_message = render_result.get("error_message")

            attempt_history.append(
                DiagramRepairAttemptRecord(
                    attempt_number=attempt_number,
                    repaired_puml_text=normalized_text,
                    validation_issues=validation_issues,
                    render_success=render_success,
                    render_error=render_failure_message,
                    backend_metadata=backend_metadata,
                )
            )

            if render_success:
                return DiagramRepairResult(
                    success=True,
                    repaired_puml_text=normalized_text,
                    attempts_used=attempt_number,
                    attempt_history=attempt_history,
                    metadata={
                        "last_backend_metadata": last_backend_metadata,
                    },
                ).model_dump()

            current_failed_puml = normalized_text
            current_render_error = render_failure_message or "Unknown render failure."

        return DiagramRepairResult(
            success=False,
            repaired_puml_text=None,
            attempts_used=len(attempt_history),
            attempt_history=attempt_history,
            metadata={
                "last_backend_metadata": last_backend_metadata,
            },
        ).model_dump()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_repair_prompt(
        self,
        *,
        original_prompt_text: str,
        current_puml_text: str,
        render_error: str | None,
    ) -> str:
        """
        Build a targeted repair prompt for PlantUML correction.
        """
        render_error_text = render_error or "Unknown render failure."

        return (
            "# DIAGRAM REPAIR TASK\n"
            "You are repairing PlantUML source that failed validation or rendering.\n\n"
            "# ORIGINAL GENERATION PROMPT\n"
            f"{original_prompt_text}\n\n"
            "# CURRENT FAILED PLANTUML\n"
            f"{current_puml_text}\n\n"
            "# RENDER/VALIDATION ERROR\n"
            f"{render_error_text}\n\n"
            "# REQUIREMENTS\n"
            "- Return only repaired PlantUML source.\n"
            "- Preserve the intended diagram meaning as much as possible.\n"
            "- Ensure the source is valid PlantUML.\n"
            "- Do not add explanations or markdown fences.\n"
        ).strip()

    def _coerce_backend_result(
        self,
        backend_result: str | dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        """
        Normalize backend output into `(text, metadata)`.
        """
        if isinstance(backend_result, str):
            return backend_result, {}

        if isinstance(backend_result, dict):
            text = backend_result.get("text")
            if not isinstance(text, str):
                raise ValueError(
                    "Repair backend dictionary response must include a string `text` field."
                )

            metadata = {key: value for key, value in backend_result.items() if key != "text"}
            return text, metadata

        raise TypeError(
            "Unsupported backend result type. Expected `str` or `dict[str, Any]`."
        )