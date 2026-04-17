"""
Segmentation service for Stage 6.

This service deterministically splits enriched markdown into section containers
using H1/H2 boundaries, computes stable section IDs, derives structural signals,
and applies a rule-based 10-type section taxonomy.

The logic intentionally remains deterministic because Stage 6 is part of the
retrieval-critical ingestion backbone.
"""

from __future__ import annotations

import re
import unicodedata
from time import perf_counter

from backend.modules.ingestion.contracts.stage_1_contracts import StageWarning
from backend.modules.ingestion.contracts.stage_6_contracts import (
    SectionType,
    SegmentedSection,
    Stage6Input,
    Stage6Metrics,
    Stage6Output,
    StructuralSignals,
)


class SegmentationService:
    """Service that performs deterministic Stage 6 section segmentation."""

    _HEADING_PATTERN = re.compile(r"^(#{1,2})\s+(?P<heading>\S.*)$", re.MULTILINE)
    _TABLE_PATTERN = re.compile(r"(?m)^\s*\|.+\|\s*$")
    _LIST_PATTERN = re.compile(r"(?m)^\s*(?:[-*+]\s+|\d+\.\s+).+")
    _REQUIREMENT_ID_PATTERN = re.compile(
        r"\b(?:REQ|FR|NFR|BR|US|STORY|R)[-_ ]?\d+\b",
        re.IGNORECASE,
    )
    _ASSET_REFERENCE_PATTERN = re.compile(r"!\[[^\]]*\]\([^)]+\)|<img\b|\[VISION_EXTRACTED:", re.IGNORECASE)
    _H3_PATTERN = re.compile(r"(?m)^###\s+\S+")
    _WORD_PATTERN = re.compile(r"\S+")

    def segment_document(self, request: Stage6Input) -> Stage6Output:
        """Split enriched markdown into deterministic sections."""
        start_time = perf_counter()
        sections = self._split_markdown_into_sections(request.enriched_markdown)

        total_duration_ms = (perf_counter() - start_time) * 1000
        metrics = Stage6Metrics(
            total_sections=len(sections),
            heading_matched_sections=sum(1 for section in sections if section.heading_level in {1, 2}),
            synthetic_sections=sum(1 for section in sections if section.heading_level == 0),
            total_duration_ms=round(total_duration_ms, 3),
        )

        return Stage6Output(
            process_id=request.process_id,
            document_id=request.document_id,
            source_blob=request.source_blob,
            enriched_markdown_artifact=request.enriched_markdown_artifact,
            sections=sections,
            warnings=list(request.prior_warnings),
            metrics=metrics,
        )

    def _split_markdown_into_sections(self, markdown_text: str) -> list[SegmentedSection]:
        matches = list(self._HEADING_PATTERN.finditer(markdown_text))

        if not matches:
            return [self._build_synthetic_root_section(markdown_text)]

        sections: list[SegmentedSection] = []

        for section_index, match in enumerate(matches, start=1):
            heading_marker = match.group(1)
            heading_level = len(heading_marker)
            heading_text = match.group("heading").strip()
            section_start = match.start()

            if section_index < len(matches):
                section_end = matches[section_index].start()
            else:
                section_end = len(markdown_text)

            raw_content = markdown_text[section_start:section_end].strip()
            preview_text = self._build_preview_text(raw_content)
            structural_signals = self._detect_structural_signals(raw_content)
            section_type = self._classify_section_type(heading_text, preview_text)

            sections.append(
                SegmentedSection(
                    section_id=self._build_section_id(section_index, heading_text),
                    heading=heading_text,
                    heading_level=heading_level,
                    section_index=section_index,
                    section_type=section_type,
                    raw_content=raw_content,
                    preview_text=preview_text,
                    structural_signals=structural_signals,
                    warnings=[],
                )
            )

        return sections

    def _build_synthetic_root_section(self, markdown_text: str) -> SegmentedSection:
        raw_content = markdown_text.strip()
        preview_text = self._build_preview_text(raw_content)
        return SegmentedSection(
            section_id="section_001_document_root",
            heading="Document Root",
            heading_level=0,
            section_index=1,
            section_type=SectionType.OVERVIEW,
            raw_content=raw_content,
            preview_text=preview_text,
            structural_signals=self._detect_structural_signals(raw_content),
            warnings=[
                StageWarning(
                    code="SYNTHETIC_ROOT_SECTION_CREATED",
                    message="No H1/H2 headings were found; a synthetic root section was created.",
                    details={},
                )
            ],
        )

    def _build_preview_text(self, raw_content: str, max_length: int = 240) -> str:
        lines = [line.strip() for line in raw_content.splitlines() if line.strip()]
        non_heading_lines = [line for line in lines if not line.startswith("#")]
        source_lines = non_heading_lines or lines

        preview = " ".join(source_lines[:2]).strip()
        if not preview:
            preview = raw_content.strip()

        if len(preview) > max_length:
            return preview[: max_length - 3].rstrip() + "..."

        return preview

    def _detect_structural_signals(self, raw_content: str) -> StructuralSignals:
        word_count = len(self._WORD_PATTERN.findall(raw_content))
        estimated_tokens = max(1, round(word_count * 1.3))

        return StructuralSignals(
            has_table=bool(self._TABLE_PATTERN.search(raw_content)),
            has_list=bool(self._LIST_PATTERN.search(raw_content)),
            has_requirement_pattern=bool(self._REQUIREMENT_ID_PATTERN.search(raw_content)),
            has_asset_reference=bool(self._ASSET_REFERENCE_PATTERN.search(raw_content)),
            has_h3_subheading=bool(self._H3_PATTERN.search(raw_content)),
            estimated_tokens=estimated_tokens,
        )

    def _classify_section_type(self, heading: str, preview_text: str) -> SectionType:
        text = f"{heading} {preview_text}".lower()

        keyword_map: list[tuple[SectionType, tuple[str, ...]]] = [
            (
                SectionType.REQUIREMENTS,
                ("requirement", "user story", "acceptance criteria", "functional requirement", "nfr"),
            ),
            (
                SectionType.ARCHITECTURE,
                ("architecture", "component", "system design", "deployment architecture"),
            ),
            (
                SectionType.PROCESS_FLOW,
                ("process flow", "workflow", "sequence", "flowchart", "journey"),
            ),
            (
                SectionType.DATA_MODEL,
                ("data model", "entity", "schema", "table design", "database"),
            ),
            (
                SectionType.API_SPECIFICATION,
                ("api", "endpoint", "request", "response", "payload", "swagger"),
            ),
            (
                SectionType.INTEGRATION,
                ("integration", "interface", "external system", "upstream", "downstream"),
            ),
            (
                SectionType.SECURITY,
                ("security", "authentication", "authorization", "access control", "encryption"),
            ),
            (
                SectionType.TESTING,
                ("test", "uat", "validation", "verification", "test case"),
            ),
            (
                SectionType.RISKS_ASSUMPTIONS_CONSTRAINTS,
                ("risk", "assumption", "constraint", "dependency", "limitation"),
            ),
            (
                SectionType.OVERVIEW,
                ("overview", "summary", "introduction", "scope", "background"),
            ),
        ]

        for section_type, keywords in keyword_map:
            if any(keyword in text for keyword in keywords):
                return section_type

        return SectionType.OVERVIEW

    def _build_section_id(self, section_index: int, heading: str) -> str:
        slug = self._slugify(heading)
        return f"section_{section_index:03d}_{slug}"

    def _slugify(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
        lowered = normalized.lower()
        lowered = re.sub(r"[^a-z0-9]+", "_", lowered).strip("_")
        return lowered or "untitled"