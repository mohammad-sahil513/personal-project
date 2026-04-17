"""
Diagram generator for the Generation module.

Responsibilities:
- Execute the active `diagram_plantuml` strategy
- Accept an already assembled prompt
- Generate canonical PlantUML source
- Normalize and validate the PlantUML source
- Render the diagram
- Trigger bounded repair if rendering fails
- Persist artifacts
- Return embed-ready diagram output as SectionOutput
- Emit shared observability logs for the diagram runtime path

Important:
- This file orchestrates the diagram runtime path only.
- It does NOT perform generic text/table correction logic.
- It does NOT handle section orchestration / Retrieval / export logic.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.modules.generation.contracts.generation_contracts import (
    DiagramArtifactRefs,
    GenerationStrategy,
    OutputType,
    SectionOutput,
)
from backend.modules.observability.services.logging_service import (
    LoggingService,
)


# ------------------------------------------------------------------------------
# Protocols for injected runtime components
# ------------------------------------------------------------------------------


@runtime_checkable
class DiagramSourceBackend(Protocol):
    """
    Backend responsible for generating canonical PlantUML text from a prompt.
    """

    def generate_puml(
        self,
        prompt: str,
        *,
        model_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str | dict[str, Any]:
        """
        Returns either:
        - raw PlantUML text as a string
        - or a mapping with at least a `text` field and optional metadata
        """
        ...


@runtime_checkable
class PlantUMLNormalizer(Protocol):
    """
    Normalizes raw/generated PlantUML text before validation/render.
    """

    def normalize(self, puml_text: str) -> str:
        """
        Return normalized PlantUML source text.
        """
        ...


@runtime_checkable
class PlantUMLValidator(Protocol):
    """
    Validates/lints normalized PlantUML source before render.
    """

    def validate(self, puml_text: str) -> tuple[bool, list[str]]:
        """
        Returns:
        - bool: whether the PlantUML is acceptable for rendering
        - list of validation issues/warnings
        """
        ...


@runtime_checkable
class DiagramRenderer(Protocol):
    """
    Renders PlantUML source into concrete artifacts (e.g. SVG/PNG).
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


@runtime_checkable
class DiagramRepairLoop(Protocol):
    """
    Repairs PlantUML when render fails.
    """

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
        Expected keys:
        - success: bool
        - repaired_puml_text: str | None
        - attempts_used: int
        - metadata: dict[str, Any]
        """
        ...


@runtime_checkable
class DiagramArtifactStore(Protocol):
    """
    Persists diagram artifacts and returns artifact references/paths.
    """

    def store(
        self,
        *,
        section_id: str,
        normalized_puml_text: str,
        repaired_puml_versions: list[str],
        svg_content: str | bytes | None,
        png_content: bytes | None,
        metadata: dict[str, Any] | None = None,
    ) -> DiagramArtifactRefs:
        """
        Persist diagram artifacts and return their references.
        """
        ...


@runtime_checkable
class DiagramEmbedder(Protocol):
    """
    Prepares embed/export metadata from stored diagram artifacts.
    """

    def prepare_embed_metadata(
        self,
        *,
        section_id: str,
        artifacts: DiagramArtifactRefs,
    ) -> dict[str, Any]:
        """
        Return embed/export metadata for downstream assembly/export usage.
        """
        ...


# ------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------


class DiagramGenerationRequest(BaseModel):
    """
    Request payload for one diagram-generation operation.
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
        description="Optional generation metadata passed across the diagram runtime path.",
    )

    @field_validator("prompt_text")
    @classmethod
    def validate_prompt_text(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("prompt_text cannot be empty.")
        return value


class DiagramGenerationResponse(BaseModel):
    """
    Structured response from the diagram generator.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="Stable target section identifier.")
    strategy: GenerationStrategy = Field(
        default=GenerationStrategy.DIAGRAM_PLANTUML,
        description="The Generation strategy executed by this generator.",
    )
    output: SectionOutput = Field(
        description="Structured diagram artifact output payload."
    )
    normalized_puml_text: str = Field(
        description="Canonical normalized PlantUML source text."
    )
    validation_issues: list[str] = Field(
        default_factory=list,
        description="PlantUML validation issues/warnings.",
    )
    render_repair_used: bool = Field(
        default=False,
        description="Whether the bounded repair loop was used after an initial render failure.",
    )
    repair_attempts_used: int = Field(
        default=0,
        ge=0,
        description="Number of bounded repair attempts used.",
    )
    backend_metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Aggregated backend/runtime metadata.",
    )


# ------------------------------------------------------------------------------
# Diagram Generator
# ------------------------------------------------------------------------------


class DiagramGenerator:
    """
    Runtime executor for the active `diagram_plantuml` Generation strategy.
    """

    def __init__(
        self,
        source_backend: DiagramSourceBackend,
        normalizer: PlantUMLNormalizer,
        validator: PlantUMLValidator,
        renderer: DiagramRenderer,
        repair_loop: DiagramRepairLoop,
        artifact_store: DiagramArtifactStore,
        embedder: DiagramEmbedder,
        logging_service: LoggingService | None = None,
    ) -> None:
        if not isinstance(source_backend, DiagramSourceBackend):
            raise TypeError("source_backend must implement DiagramSourceBackend.")
        if not isinstance(normalizer, PlantUMLNormalizer):
            raise TypeError("normalizer must implement PlantUMLNormalizer.")
        if not isinstance(validator, PlantUMLValidator):
            raise TypeError("validator must implement PlantUMLValidator.")
        if not isinstance(renderer, DiagramRenderer):
            raise TypeError("renderer must implement DiagramRenderer.")
        if not isinstance(repair_loop, DiagramRepairLoop):
            raise TypeError("repair_loop must implement DiagramRepairLoop.")
        if not isinstance(artifact_store, DiagramArtifactStore):
            raise TypeError("artifact_store must implement DiagramArtifactStore.")
        if not isinstance(embedder, DiagramEmbedder):
            raise TypeError("embedder must implement DiagramEmbedder.")

        self.source_backend = source_backend
        self.normalizer = normalizer
        self.validator = validator
        self.renderer = renderer
        self.repair_loop = repair_loop
        self.artifact_store = artifact_store
        self.embedder = embedder
        self.logging_service = logging_service

    def generate(self, request: DiagramGenerationRequest) -> DiagramGenerationResponse:
        """
        Execute the full diagram-generation runtime path for one section.
        """
        # 1) Generate canonical/raw PlantUML text
        backend_result = self.source_backend.generate_puml(
            request.prompt_text,
            model_name=request.model_name,
            metadata=request.metadata,
        )
        raw_puml_text, source_backend_metadata = self._coerce_backend_result(backend_result)

        if not raw_puml_text.strip():
            raise ValueError("Generated PlantUML source is empty.")

        self._log_info(
            "generation_diagram_source_generated",
            section_id=request.section_id,
            prompt_key_used=request.prompt_key_used,
            model_name=request.model_name,
            raw_source_length=len(raw_puml_text),
        )

        # 2) Normalize
        normalized_puml_text = self.normalizer.normalize(raw_puml_text)

        self._log_info(
            "generation_diagram_normalized",
            section_id=request.section_id,
            normalized_source_length=len(normalized_puml_text),
        )

        # 3) Validate/lint before render
        is_valid, validation_issues = self.validator.validate(normalized_puml_text)
        self._log_info(
            "generation_diagram_validated",
            section_id=request.section_id,
            is_valid=is_valid,
            validation_issue_count=len(validation_issues),
        )

        if not is_valid:
            raise ValueError(
                "PlantUML validation failed before render: " + "; ".join(validation_issues)
            )

        # 4) Initial render attempt
        initial_render_result = self.renderer.render(normalized_puml_text)
        render_success = bool(initial_render_result.get("success"))
        render_repair_used = False
        repair_attempts_used = 0
        repaired_versions: list[str] = []
        final_render_result = initial_render_result
        final_puml_text = normalized_puml_text
        repair_metadata: dict[str, Any] = {}

        # 5) Repair only if render failed
        if not render_success:
            render_repair_used = True
            initial_error = initial_render_result.get("error_message")

            self._log_warning(
                "generation_diagram_render_failed",
                section_id=request.section_id,
                error_message=initial_error,
            )

            repair_result = self.repair_loop.repair(
                original_prompt_text=request.prompt_text,
                current_puml_text=normalized_puml_text,
                render_error=initial_error,
                model_name=request.model_name,
                metadata=request.metadata,
            )

            repair_success = bool(repair_result.get("success"))
            repaired_puml_text = repair_result.get("repaired_puml_text")
            repair_attempts_used = int(repair_result.get("attempts_used", 0))
            repair_metadata = repair_result.get("metadata", {}) or {}

            self._log_info(
                "generation_diagram_repair_used",
                section_id=request.section_id,
                repair_success=repair_success,
                attempts_used=repair_attempts_used,
            )

            if not repair_success or not isinstance(repaired_puml_text, str) or not repaired_puml_text.strip():
                raise ValueError(
                    "Diagram repair loop failed to produce a valid repaired PlantUML source."
                )

            repaired_normalized = self.normalizer.normalize(repaired_puml_text)
            repaired_versions.append(repaired_normalized)

            repaired_is_valid, repaired_validation_issues = self.validator.validate(repaired_normalized)
            validation_issues.extend(repaired_validation_issues)

            self._log_info(
                "generation_diagram_repaired_source_validated",
                section_id=request.section_id,
                is_valid=repaired_is_valid,
                validation_issue_count=len(repaired_validation_issues),
            )

            if not repaired_is_valid:
                raise ValueError(
                    "Repaired PlantUML validation failed: " + "; ".join(repaired_validation_issues)
                )

            final_render_result = self.renderer.render(repaired_normalized)
            if not final_render_result.get("success"):
                final_error = str(final_render_result.get("error_message"))
                self._log_error(
                    "generation_diagram_render_failed_after_repair",
                    section_id=request.section_id,
                    error_message=final_error,
                )
                raise ValueError(
                    "Diagram render failed after repair: " + final_error
                )

            final_puml_text = repaired_normalized

        svg_content = final_render_result.get("svg_content")
        png_content = final_render_result.get("png_content")

        # 6) Persist artifacts
        artifacts = self.artifact_store.store(
            section_id=request.section_id,
            normalized_puml_text=final_puml_text,
            repaired_puml_versions=repaired_versions,
            svg_content=svg_content,
            png_content=png_content,
            metadata=request.metadata,
        )

        self._log_info(
            "generation_diagram_artifacts_stored",
            section_id=request.section_id,
            puml_path=artifacts.puml_path,
            svg_path=artifacts.svg_path,
            png_path=artifacts.png_path,
            repaired_version_count=len(artifacts.repaired_puml_paths),
        )

        # 7) Prepare embed/export metadata
        embed_metadata = self.embedder.prepare_embed_metadata(
            section_id=request.section_id,
            artifacts=artifacts,
        )

        output = SectionOutput(
            output_type=OutputType.DIAGRAM_ARTIFACT,
            diagram_artifacts=artifacts,
            metadata={
                "prompt_key_used": request.prompt_key_used,
                "section_heading": request.section_heading,
                "embed_metadata": embed_metadata,
            },
        )

        aggregated_backend_metadata = {
            "source_backend": source_backend_metadata,
            "repair": repair_metadata,
            "render": {
                "repair_used": render_repair_used,
                "repair_attempts_used": repair_attempts_used,
            },
            "normalized_puml_text": final_puml_text,
        }

        self._log_info(
            "generation_diagram_completed",
            section_id=request.section_id,
            render_repair_used=render_repair_used,
            repair_attempts_used=repair_attempts_used,
        )

        return DiagramGenerationResponse(
            section_id=request.section_id,
            output=output,
            normalized_puml_text=final_puml_text,
            validation_issues=validation_issues,
            render_repair_used=render_repair_used,
            repair_attempts_used=repair_attempts_used,
            backend_metadata=aggregated_backend_metadata,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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

            metadata = {key: value for key, value in backend_result.items() if key != "text"}
            return text, metadata

        raise TypeError(
            "Unsupported backend result type. Expected `str` or `dict[str, Any]`."
        )

    def _log_info(self, event: str, **fields: Any) -> None:
        """
        Best-effort info logging.
        """
        if self.logging_service is None:
            return
        self.logging_service.info(event, **fields)

    def _log_warning(self, event: str, **fields: Any) -> None:
        """
        Best-effort warning logging.
        """
        if self.logging_service is None:
            return
        self.logging_service.warning(event, **fields)

    def _log_error(self, event: str, **fields: Any) -> None:
        """
        Best-effort error logging.
        """
        if self.logging_service is None:
            return
        self.logging_service.error(event, **fields)