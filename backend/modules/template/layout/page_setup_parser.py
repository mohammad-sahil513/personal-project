"""
Page setup parser for custom DOCX layout extraction.

This parser captures section-level page metadata required for preserving:
- orientation,
- page size,
- page margins,
- section-count continuity.
"""

from __future__ import annotations

from docx.document import Document as DocxDocument
from docx.enum.section import WD_ORIENT

from .layout_contracts import PageSetupInfo


class PageSetupParser:
    """Extract section-level page setup metadata from a DOCX document."""

    def parse(self, document: DocxDocument) -> list[PageSetupInfo]:
        """
        Parse all DOCX sections into PageSetupInfo records.
        """
        page_setups: list[PageSetupInfo] = []

        for section_index, section in enumerate(document.sections):
            orientation = (
                "landscape"
                if section.orientation == WD_ORIENT.LANDSCAPE
                else "portrait"
            )

            page_setups.append(
                PageSetupInfo(
                    section_index=section_index,
                    orientation=orientation,
                    page_width_emu=int(section.page_width or 0),
                    page_height_emu=int(section.page_height or 0),
                    margin_top_emu=int(section.top_margin or 0),
                    margin_bottom_emu=int(section.bottom_margin or 0),
                    margin_left_emu=int(section.left_margin or 0),
                    margin_right_emu=int(section.right_margin or 0),
                )
            )

        return page_setups