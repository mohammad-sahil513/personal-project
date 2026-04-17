"""
Section assembler for the Generation module.

Responsibilities:
- Merge section results in template order
- Handle generated / degraded / skipped / failed sections deterministically
- Produce an assembly-friendly document representation for later TOC/export steps

Important:
- This file performs assembly only.
- It does NOT do visual styling or DOCX rendering.
- It does NOT perform export logic.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.generation.contracts.generation_contracts import (
    DiagramArtifactRefs,
    OutputType,
    SectionExecutionStatus,
    SectionGenerationResult,
)


class AssembledSection(BaseModel):
    """
    One section in the assembled document representation.
    """

    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(description="Stable section identifier.")
    section_heading: str | None = Field(default=None, description="Section heading/title.")
    status: SectionExecutionStatus = Field(description="Final section execution status.")
    included: bool = Field(
        description="Whether the section is included in the assembled output representation."
    )
    markdown_content: str | None = Field(
        default=None,
        description="Assembled markdown content for text/table/placeholder sections.",
    )
    diagram_artifacts: DiagramArtifactRefs | None = Field(
        default=None,
        description="Diagram artifact references for diagram sections.",
    )
    placeholder_reason: str | None = Field(
        default=None,
        description="Reason for deterministic placeholder content when applicable.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional assembly metadata for downstream TOC/export handling.",
    )


class SectionAssemblyRequest(BaseModel):
    """
    Input payload for document-level section assembly.
    """

    model_config = ConfigDict(extra="forbid")

    ordered_section_ids: list[str] = Field(
        default_factory=list,
        description="Template-defined section order for final assembly.",
    )
    section_results: list[SectionGenerationResult] = Field(
        default_factory=list,
        description="Completed section generation results.",
    )
    include_failed_placeholders: bool = Field(
        default=True,
        description="Whether failed sections should be represented with deterministic placeholders.",
    )
    include_skipped_placeholders: bool = Field(
        default=True,
        description="Whether skipped sections should be represented with deterministic placeholders.",
    )
    include_degraded_sections: bool = Field(
        default=True,
        description="Whether degraded sections should still be included in assembled output.",
    )


class SectionAssemblyResult(BaseModel):
    """
    Output payload from section assembly.

    This is a document-level intermediate representation to be used by:
    - TOC generation
    - structural normalization
    - export routing
    """

    model_config = ConfigDict(extra="forbid")

    assembled_sections: list[AssembledSection] = Field(default_factory=list)
    assembled_markdown: str = Field(
        default="",
        description="Combined markdown representation of the assembled document.",
    )
    included_section_count: int = Field(default=0, ge=0)
    omitted_section_count: int = Field(default=0, ge=0)
    diagram_section_count: int = Field(default=0, ge=0)


class SectionAssembler:
    """
    Deterministically assemble section results into document-level structure.
    """

    def assemble(self, request: SectionAssemblyRequest) -> SectionAssemblyResult:
        """
        Merge section results in template order and produce assembled markdown.

        Rules:
        - preserve template order from ordered_section_ids
        - include GENERATED sections
        - include DEGRADED sections when include_degraded_sections=True
        - include SKIPPED / FAILED placeholders when corresponding flags are enabled
        - represent diagrams using deterministic marker blocks for later export embedding
        """
        result_map = {result.section_id: result for result in request.section_results}

        assembled_sections: list[AssembledSection] = []

        for section_id in request.ordered_section_ids:
            result = result_map.get(section_id)
            if result is None:
                # Missing results are omitted silently here; orchestration should normally prevent this.
                continue

            assembled_section = self._assemble_one(
                result=result,
                include_failed_placeholders=request.include_failed_placeholders,
                include_skipped_placeholders=request.include_skipped_placeholders,
                include_degraded_sections=request.include_degraded_sections,
            )
            assembled_sections.append(assembled_section)

        assembled_markdown = self._join_markdown_sections(assembled_sections)

        included_count = sum(1 for section in assembled_sections if section.included)
        omitted_count = sum(1 for section in assembled_sections if not section.included)
        diagram_count = sum(
            1 for section in assembled_sections if section.diagram_artifacts is not None
        )

        return SectionAssemblyResult(
            assembled_sections=assembled_sections,
            assembled_markdown=assembled_markdown,
            included_section_count=included_count,
            omitted_section_count=omitted_count,
            diagram_section_count=diagram_count,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _assemble_one(
        self,
        *,
        result: SectionGenerationResult,
        include_failed_placeholders: bool,
        include_skipped_placeholders: bool,
        include_degraded_sections: bool,
    ) -> AssembledSection:
        """
        Assemble one section result into document-level representation.
        """
        heading = result.section_heading or result.section_id

        # GENERATED / DEGRADED markdown and tables
        if result.status in {
            SectionExecutionStatus.GENERATED,
            SectionExecutionStatus.DEGRADED,
        }:
            if result.status == SectionExecutionStatus.DEGRADED and not include_degraded_sections:
                return AssembledSection(
                    section_id=result.section_id,
                    section_heading=heading,
                    status=result.status,
                    included=False,
                    markdown_content=None,
                    diagram_artifacts=None,
                    placeholder_reason="degraded_section_omitted",
                    metadata={},
                )

            if result.output is None:
                return AssembledSection(
                    section_id=result.section_id,
                    section_heading=heading,
                    status=result.status,
                    included=False,
                    markdown_content=None,
                    diagram_artifacts=None,
                    placeholder_reason="missing_output",
                    metadata={},
                )

            if result.output.output_type in {OutputType.MARKDOWN_TEXT, OutputType.MARKDOWN_TABLE}:
                return AssembledSection(
                    section_id=result.section_id,
                    section_heading=heading,
                    status=result.status,
                    included=True,
                    markdown_content=result.output.content_markdown,
                    diagram_artifacts=None,
                    placeholder_reason=None,
                    metadata=result.output.metadata,
                )

            # Diagram output
            if result.output.output_type == OutputType.DIAGRAM_ARTIFACT:
                marker_block = self._diagram_marker_block(
                    section_id=result.section_id,
                    heading=heading,
                )
                return AssembledSection(
                    section_id=result.section_id,
                    section_heading=heading,
                    status=result.status,
                    included=True,
                    markdown_content=marker_block,
                    diagram_artifacts=result.output.diagram_artifacts,
                    placeholder_reason=None,
                    metadata=result.output.metadata,
                )

        # SKIPPED
        if result.status == SectionExecutionStatus.SKIPPED:
            if not include_skipped_placeholders:
                return AssembledSection(
                    section_id=result.section_id,
                    section_heading=heading,
                    status=result.status,
                    included=False,
                    markdown_content=None,
                    diagram_artifacts=None,
                    placeholder_reason="skipped_section_omitted",
                    metadata={},
                )

            return AssembledSection(
                section_id=result.section_id,
                section_heading=heading,
                status=result.status,
                included=True,
                markdown_content=self._placeholder_block(
                    heading=heading,
                    reason="Section was skipped during generation.",
                ),
                diagram_artifacts=None,
                placeholder_reason="skipped",
                metadata={},
            )

        # FAILED
        if result.status == SectionExecutionStatus.FAILED:
            if not include_failed_placeholders:
                return AssembledSection(
                    section_id=result.section_id,
                    section_heading=heading,
                    status=result.status,
                    included=False,
                    markdown_content=None,
                    diagram_artifacts=None,
                    placeholder_reason="failed_section_omitted",
                    metadata={},
                )

            return AssembledSection(
                section_id=result.section_id,
                section_heading=heading,
                status=result.status,
                included=True,
                markdown_content=self._placeholder_block(
                    heading=heading,
                    reason="Section failed during generation and requires manual review.",
                ),
                diagram_artifacts=None,
                placeholder_reason="failed",
                metadata={"error_message": result.error_message},
            )

        # Non-terminal / unexpected states are omitted at assembly time
        return AssembledSection(
            section_id=result.section_id,
            section_heading=heading,
            status=result.status,
            included=False,
            markdown_content=None,
            diagram_artifacts=None,
            placeholder_reason="non_terminal_or_unexpected_status",
            metadata={},
        )

    def _join_markdown_sections(self, sections: list[AssembledSection]) -> str:
        """
        Join included markdown sections into one document-level markdown string.
        """
        parts: list[str] = []

        for section in sections:
            if not section.included:
                continue
            if not section.markdown_content:
                continue
            parts.append(section.markdown_content.strip())

        return "\n\n".join(part for part in parts if part).strip()

    def _placeholder_block(self, *, heading: str, reason: str) -> str:
        """
        Deterministic markdown placeholder block for skipped/failed sections.
        """
        return f"## {heading}\n\n[PLACEHOLDER]\n\n{reason}"

    def _diagram_marker_block(self, *, section_id: str, heading: str) -> str:
        """
        Deterministic markdown marker used to preserve diagram placement for later export.
        """
        return f"## {heading}\n\n[[DIAGRAM:{section_id}]]"