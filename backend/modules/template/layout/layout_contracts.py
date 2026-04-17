"""
Layout extraction contracts for custom DOCX templates.

These contracts define the metadata shape produced by the Template-side layout
extraction layer and consumed later by rendering/export flows.

Design goals:
- preserve section/page metadata,
- preserve header/footer metadata,
- preserve style and table metadata,
- expose triple-anchor-friendly heading metadata,
- keep version continuity visible at the contract layer.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AnchorMetadata(BaseModel):
    """
    Anchor metadata for a heading-like insertion point in the template DOCX.

    Triple-anchor intent:
    1. XML-level identity where available,
    2. structural heading match,
    3. normalized heading text for fuzzy fallback later.
    """

    model_config = ConfigDict(extra="forbid")

    anchor_id: str = Field(..., min_length=1)
    section_index: int = Field(..., ge=0)
    paragraph_index: int = Field(..., ge=0)
    heading_text: str = Field(..., min_length=1)
    normalized_heading_text: str = Field(..., min_length=1)
    xml_element_id: str | None = None
    anchor_order: int = Field(..., ge=0)


class PageSetupInfo(BaseModel):
    """Section-level page setup extracted from a DOCX template."""

    model_config = ConfigDict(extra="forbid")

    section_index: int = Field(..., ge=0)
    orientation: str = Field(..., min_length=1)
    page_width_emu: int = Field(..., ge=0)
    page_height_emu: int = Field(..., ge=0)
    margin_top_emu: int = Field(..., ge=0)
    margin_bottom_emu: int = Field(..., ge=0)
    margin_left_emu: int = Field(..., ge=0)
    margin_right_emu: int = Field(..., ge=0)


class HeaderFooterContent(BaseModel):
    """Section-level header/footer metadata extracted from DOCX."""

    model_config = ConfigDict(extra="forbid")

    section_index: int = Field(..., ge=0)
    header_text: str = ""
    footer_text: str = ""
    header_linked_to_previous: bool = False
    footer_linked_to_previous: bool = False


class StyleDefinition(BaseModel):
    """Simplified metadata for a DOCX style definition."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    style_type: str = Field(..., min_length=1)
    base_style_name: str | None = None
    builtin: bool = False


class TableFormatInfo(BaseModel):
    """Lightweight formatting metadata for one table in the DOCX."""

    model_config = ConfigDict(extra="forbid")

    table_index: int = Field(..., ge=0)
    row_count: int = Field(..., ge=0)
    column_count: int = Field(..., ge=0)
    style_name: str | None = None


class LayoutManifest(BaseModel):
    """
    Versioned layout manifest for a custom template.

    Atomic version sync across:
    - compiled template JSON,
    - layout manifest,
    - shell DOCX
    is enforced later through repository/orchestration flows. This contract
    captures the expected metadata shape.
    """

    model_config = ConfigDict(extra="forbid")

    template_id: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    source_docx_path: str = Field(..., min_length=1)
    section_count: int = Field(..., ge=0)

    anchors: list[AnchorMetadata] = Field(default_factory=list)
    page_setups: list[PageSetupInfo] = Field(default_factory=list)
    headers_footers: list[HeaderFooterContent] = Field(default_factory=list)
    styles: list[StyleDefinition] = Field(default_factory=list)
    tables: list[TableFormatInfo] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_anchor_ids_unique(self) -> "LayoutManifest":
        """Ensure anchor_id values remain unique inside the manifest."""
        seen: set[str] = set()
        duplicates: set[str] = set()

        for anchor in self.anchors:
            if anchor.anchor_id in seen:
                duplicates.add(anchor.anchor_id)
            seen.add(anchor.anchor_id)

        if duplicates:
            raise ValueError(f"Duplicate anchor_id values are not allowed: {sorted(duplicates)}")

        return self