"""
Table generator for the Generation module.

Responsibilities:
- Execute the active `generate_table` strategy
- Accept an already assembled prompt
- Invoke an injected LLM backend / Semantic Kernel adapter
- Return deterministic markdown table content as SectionOutput

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
class TableGenerationBackend(Protocol):
    """
    Protocol for an injected table-generation backend.

    This keeps the generator decoupled from the concrete Semantic Kernel adapter
    while still allowing production wiring later.
    """

    def generate_table(
        self,
        prompt: str,
        *,
        model_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | dict[str, Any]:
        """
        Generate table content for the supplied prompt.

        Returns either:
        - a plain string containing the generated markdown table, or
        - a mapping that includes at least a `text` field and optionally metadata
        """
        ...


class TableGenerationRequest(BaseModel):
    """
    Request payload for one table-generation operation.
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


class TableGenerationResponse(BaseModel):
    """
    Structured response from the table generator.

    This response intentionally returns a SectionOutput so downstream validators,
    section executors, and assembly can use a stable Generation-owned contract.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="Stable target section identifier.")
    strategy: GenerationStrategy = Field(
        default=GenerationStrategy.GENERATE_TABLE,
        description="The Generation strategy executed by this generator.",
    )
    output: SectionOutput = Field(
        description="Structured markdown-table output payload for the generated section."
    )
    raw_table_markdown: str = Field(
        description="Normalized raw markdown table returned by the backend."
    )
    backend_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional backend response metadata such as usage/model details.",
    )


class TableGenerator:
    """
    Runtime executor for the active `generate_table` Generation strategy.

    The backend is injected so this class remains:
    - testable
    - decoupled from the concrete Semantic Kernel implementation
    - aligned with later infrastructure wiring
    """

    def __init__(self, backend: TableGenerationBackend) -> None:
        if not isinstance(backend, TableGenerationBackend):
            raise TypeError(
                "backend must implement the TableGenerationBackend protocol."
            )
        self.backend = backend

    def generate(self, request: TableGenerationRequest) -> TableGenerationResponse:
        """
        Execute table generation for a single section and return markdown-table output.
        """
        backend_result = self.backend.generate_table(
            request.prompt_text,
            model_name=request.model_name,
            metadata=request.metadata,
        )

        raw_text, backend_metadata = self._coerce_backend_result(backend_result)
        normalized_table = self._normalize_markdown_output(raw_text)

        if not normalized_table.strip():
            raise ValueError("Generated table output is empty after normalization.")

        output = SectionOutput(
            output_type=OutputType.MARKDOWN_TABLE,
            content_markdown=normalized_table,
            metadata={
                "prompt_key_used": request.prompt_key_used,
                "section_heading": request.section_heading,
            },
        )

        return TableGenerationResponse(
            section_id=request.section_id,
            output=output,
            raw_table_markdown=normalized_table,
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
        Normalize model output into clean markdown table text.

        Practical cleanup rules:
        - trim leading/trailing whitespace
        - unwrap simple fenced markdown blocks
        - preserve plain markdown content as-is

        Full table-shape validation is intentionally deferred to output_validator.py.
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
                body_lines = lines[1:-1]
                normalized = "\n".join(body_lines).strip()

        return normalized