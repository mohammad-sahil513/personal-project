"""
Text generator for the Generation module.

Responsibilities:
- Execute the active `summarize_text` strategy
- Accept an already assembled prompt
- Invoke an injected LLM backend / Semantic Kernel adapter
- Return deterministic markdown text as SectionOutput

Important:
- This file does NOT perform validation. Validation belongs to output_validator.py.
- This file does NOT implement retry. Retry belongs to correction_loop.py.
- This file does NOT apply low-evidence markers. That belongs to section_executor.py.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.generation.contracts.generation_contracts import (
    GenerationStrategy,
    OutputType,
    SectionOutput,
)


@runtime_checkable
class TextGenerationBackend(Protocol):
    """
    Protocol for an injected text-generation backend.

    This keeps the generator decoupled from the concrete Semantic Kernel adapter
    while still allowing production wiring later.
    """

    def generate_text(
        self,
        prompt: str,
        *,
        model_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | dict[str, Any]:
        """
        Generate text for the supplied prompt.

        Returns either:
        - a plain string containing the generated text, or
        - a mapping that includes at least a `text` field and optionally metadata
        """
        ...


class TextGenerationRequest(BaseModel):
    """
    Request payload for one text-generation operation.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="Stable target section identifier.")
    section_heading: str = Field(description="Target section heading/title.")
    prompt_text: str = Field(description="Fully assembled prompt text for the section.")
    prompt_key_used: str = Field(description="Prompt key used after fallback resolution.")
    model_name: str | None = Field(
        default=None,
        description="Optional backend/deployment/model name hint.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional generation metadata passed to the backend.",
    )

    @field_validator("prompt_text")
    @classmethod
    def validate_prompt_text(cls, value: str) -> str:
        """
        Ensure prompt text is not empty.
        """
        if not value or not value.strip():
            raise ValueError("prompt_text cannot be empty.")
        return value


class TextGenerationResponse(BaseModel):
    """
    Structured response from the text generator.

    This response intentionally returns a SectionOutput so downstream validators,
    section executors, and assembly can use a stable Generation-owned contract.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="Stable target section identifier.")
    strategy: GenerationStrategy = Field(
        default=GenerationStrategy.SUMMARIZE_TEXT,
        description="The Generation strategy executed by this generator.",
    )
    output: SectionOutput = Field(
        description="Structured markdown output payload for the generated section."
    )
    raw_text: str = Field(
        description="Normalized raw markdown text returned by the backend."
    )
    backend_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional backend response metadata such as usage/model details.",
    )


class TextGenerator:
    """
    Runtime executor for the active `summarize_text` Generation strategy.

    The backend is injected so this class remains:
    - testable
    - decoupled from the concrete Semantic Kernel implementation
    - aligned with later infrastructure wiring
    """

    def __init__(self, backend: TextGenerationBackend) -> None:
        if not isinstance(backend, TextGenerationBackend):
            raise TypeError(
                "backend must implement the TextGenerationBackend protocol."
            )
        self.backend = backend

    def generate(self, request: TextGenerationRequest) -> TextGenerationResponse:
        """
        Execute text generation for a single section and return markdown output.
        """
        backend_result = self.backend.generate_text(
            request.prompt_text,
            model_name=request.model_name,
            metadata=request.metadata,
        )

        raw_text, backend_metadata = self._coerce_backend_result(backend_result)
        normalized_text = self._normalize_markdown_output(raw_text)

        if not normalized_text.strip():
            raise ValueError("Generated text output is empty after normalization.")

        output = SectionOutput(
            output_type=OutputType.MARKDOWN_TEXT,
            content_markdown=normalized_text,
            metadata={
                "prompt_key_used": request.prompt_key_used,
                "section_heading": request.section_heading,
            },
        )

        return TextGenerationResponse(
            section_id=request.section_id,
            output=output,
            raw_text=normalized_text,
            backend_metadata=backend_metadata,
        )

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
        Normalize model output into clean markdown text.

        Practical cleanup rules:
        - trim leading/trailing whitespace
        - unwrap simple fenced markdown blocks
        - preserve plain markdown content as-is
        """
        normalized = text.strip()

        # Unwrap common fenced-markdown responses:
        # ```markdown
        # ...
        # ```
        # or
        # ```
        # ...
        # ```
        if normalized.startswith("```") and normalized.endswith("```"):
            lines = normalized.splitlines()

            if len(lines) >= 2:
                # Remove first and last fence lines
                body_lines = lines[1:-1]

                # If the opening fence was ```markdown, the first line of content is already body_lines[0]
                normalized = "\n".join(body_lines).strip()

        return normalized