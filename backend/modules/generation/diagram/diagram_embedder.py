"""
Diagram embedder for the Generation module.

Responsibilities:
- Convert stored diagram artifacts into embed/export-ready metadata
- Select a preferred artifact format for downstream embedding
- Return deterministic metadata for later assembly/export integration

Important:
- This file is metadata-preparation only.
- It does NOT normalize, validate, render, repair, or persist artifacts.
- It does NOT perform DOCX/PDF embedding itself; that happens later in assembly/export/rendering.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.generation.contracts.generation_contracts import DiagramArtifactRefs


class DiagramEmbedFormat(str, Enum):
    """
    Preferred artifact format for downstream embedding/export.
    """

    PNG = "png"
    SVG = "svg"


class DiagramEmbedMetadata(BaseModel):
    """
    Stable metadata contract prepared for downstream assembly/export.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="Owning section identifier.")
    preferred_embed_format: DiagramEmbedFormat = Field(
        description="Preferred format for downstream embedding."
    )
    png_path: str | None = Field(
        default=None,
        description="PNG artifact path/reference, if available.",
    )
    svg_path: str | None = Field(
        default=None,
        description="SVG artifact path/reference, if available.",
    )
    puml_path: str | None = Field(
        default=None,
        description="Canonical PlantUML source path/reference.",
    )
    manifest_path: str | None = Field(
        default=None,
        description="Diagram manifest path/reference.",
    )
    width_hint_px: int | None = Field(
        default=None,
        ge=1,
        description="Optional downstream width hint for render/export embedding.",
    )
    height_hint_px: int | None = Field(
        default=None,
        ge=1,
        description="Optional downstream height hint for render/export embedding.",
    )


class DiagramEmbedderService:
    """
    Prepare deterministic embed/export metadata from stored diagram artifacts.

    Preference rules:
    - PNG is preferred for DOCX/PDF embedding when available.
    - SVG is preferred only when PNG is missing and SVG is available.
    - At least one concrete render artifact (PNG or SVG) must exist.
    """

    def prepare_embed_metadata(
        self,
        *,
        section_id: str,
        artifacts: DiagramArtifactRefs,
        width_hint_px: int | None = None,
        height_hint_px: int | None = None,
    ) -> dict[str, object]:
        """
        Produce embed/export-ready metadata for one diagram section.
        """
        if not section_id or not section_id.strip():
            raise ValueError("section_id cannot be empty.")

        if artifacts is None:
            raise ValueError("artifacts cannot be None.")

        if not artifacts.png_path and not artifacts.svg_path:
            raise ValueError(
                "At least one render artifact (png_path or svg_path) is required for embedding."
            )

        preferred_format = (
            DiagramEmbedFormat.PNG
            if artifacts.png_path
            else DiagramEmbedFormat.SVG
        )

        metadata = DiagramEmbedMetadata(
            section_id=section_id,
            preferred_embed_format=preferred_format,
            png_path=artifacts.png_path,
            svg_path=artifacts.svg_path,
            puml_path=artifacts.puml_path,
            manifest_path=artifacts.manifest_path,
            width_hint_px=width_hint_px,
            height_hint_px=height_hint_px,
        )

        return metadata.model_dump()