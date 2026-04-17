"""
TOC generator for the Generation module.

Responsibilities:
- Generate a deterministic table-of-contents representation from assembled sections
- Preserve assembled/template order
- Derive heading levels from assembled markdown when possible
- Produce a simple markdown TOC plus structured TOC entries

Important:
- This file is TOC-only.
- It does NOT perform DOCX rendering, page numbering, or export logic.
- It consumes assembled sections from the assembly layer.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.generation.assembly.section_assembler import AssembledSection


class TOCEntry(BaseModel):
    """
    One entry in the generated table of contents.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="Stable section identifier.")
    heading: str = Field(description="Display heading used in the TOC.")
    level: int = Field(
        ge=2,
        le=3,
        description="Markdown heading level represented in the TOC (2 or 3).",
    )
    anchor: str = Field(
        description="Deterministic anchor/slug for downstream export/render usage.",
    )
    included: bool = Field(
        default=True,
        description="Whether this entry is included in the rendered TOC output.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional extra metadata for downstream use.",
    )


class TOCGenerationRequest(BaseModel):
    """
    Input payload for TOC generation.
    """

    model_config = ConfigDict(extra="forbid")

    assembled_sections: list[AssembledSection] = Field(
        default_factory=list,
        description="Assembled sections in final document order.",
    )
    include_placeholder_sections: bool = Field(
        default=True,
        description="Whether placeholder-backed sections should still appear in the TOC.",
    )
    indent_unit: str = Field(
        default="  ",
        description="Indent unit used for nested TOC markdown rendering.",
    )


class TOCGenerationResult(BaseModel):
    """
    Result of TOC generation.
    """

    model_config = ConfigDict(extra="forbid")

    toc_entries: list[TOCEntry] = Field(default_factory=list)
    toc_markdown: str = Field(
        default="",
        description="Deterministic markdown representation of the TOC.",
    )
    included_entry_count: int = Field(default=0, ge=0)


class TOCGenerator:
    """
    Deterministic TOC generator for assembled document sections.
    """

    _HEADING_RE = re.compile(r"^(##|###)\s+(.*)$")
    _LOW_EVIDENCE_RE = re.compile(r"^\[LOW EVIDENCE\]\s*$")
    _PLACEHOLDER_RE = re.compile(r"^\[PLACEHOLDER\]\s*$")

    def generate(self, request: TOCGenerationRequest) -> TOCGenerationResult:
        """
        Generate TOC entries and a markdown TOC representation.
        """
        toc_entries: list[TOCEntry] = []

        for section in request.assembled_sections:
            if not section.included:
                continue

            if (
                not request.include_placeholder_sections
                and section.placeholder_reason is not None
            ):
                continue

            heading = section.section_heading or section.section_id
            level = self._infer_heading_level(section)
            anchor = self._slugify_anchor(heading, section.section_id)

            toc_entries.append(
                TOCEntry(
                    section_id=section.section_id,
                    heading=heading,
                    level=level,
                    anchor=anchor,
                    included=True,
                    metadata={
                        "status": section.status.value,
                        "placeholder_reason": section.placeholder_reason,
                    },
                )
            )

        toc_markdown = self._render_markdown_toc(
            toc_entries=toc_entries,
            indent_unit=request.indent_unit,
        )

        return TOCGenerationResult(
            toc_entries=toc_entries,
            toc_markdown=toc_markdown,
            included_entry_count=len(toc_entries),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _infer_heading_level(self, section: AssembledSection) -> int:
        """
        Infer heading level from assembled markdown when possible.

        Rules:
        - first heading found as ## -> level 2
        - first heading found as ### -> level 3
        - fallback -> level 2
        """
        content = (section.markdown_content or "").strip()
        if not content:
            return 2

        for raw_line in content.splitlines():
            line = raw_line.strip()

            if not line:
                continue
            if self._LOW_EVIDENCE_RE.match(line):
                continue
            if self._PLACEHOLDER_RE.match(line):
                continue

            match = self._HEADING_RE.match(line)
            if match:
                heading_marks = match.group(1)
                return 3 if heading_marks == "###" else 2

        return 2

    def _slugify_anchor(self, heading: str, section_id: str) -> str:
        """
        Build a deterministic anchor/slug from heading with section_id fallback suffix
        to reduce collision risk.
        """
        raw = heading.strip().lower()
        raw = re.sub(r"[^a-z0-9\s-]", "", raw)
        raw = re.sub(r"\s+", "-", raw).strip("-")

        if not raw:
            raw = section_id.lower()

        return f"{raw}-{section_id.lower()}"

    def _render_markdown_toc(
        self,
        *,
        toc_entries: list[TOCEntry],
        indent_unit: str,
    ) -> str:
        """
        Render a simple markdown TOC.

        Level 2 -> top-level bullet
        Level 3 -> one indented bullet
        """
        lines: list[str] = []

        for entry in toc_entries:
            if not entry.included:
                continue

            indent = "" if entry.level == 2 else indent_unit
            lines.append(f"{indent}- [{entry.heading}](#{entry.anchor})")

        return "\n".join(lines).strip()