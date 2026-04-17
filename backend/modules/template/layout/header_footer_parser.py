"""
Header/footer parser for custom DOCX layout extraction.

This parser preserves section-level header/footer text and linkage metadata so
the shell builder and later rendering phases can keep corporate section
formatting intact.
"""

from __future__ import annotations

from docx.document import Document as DocxDocument

from .layout_contracts import HeaderFooterContent


class HeaderFooterParser:
    """Extract section-level header/footer metadata from DOCX."""

    def parse(self, document: DocxDocument) -> list[HeaderFooterContent]:
        """
        Parse all DOCX sections into header/footer metadata.
        """
        results: list[HeaderFooterContent] = []

        for section_index, section in enumerate(document.sections):
            header_text = self._join_paragraph_text(section.header.paragraphs)
            footer_text = self._join_paragraph_text(section.footer.paragraphs)

            results.append(
                HeaderFooterContent(
                    section_index=section_index,
                    header_text=header_text,
                    footer_text=footer_text,
                    header_linked_to_previous=bool(section.header.is_linked_to_previous),
                    footer_linked_to_previous=bool(section.footer.is_linked_to_previous),
                )
            )

        return results

    @staticmethod
    def _join_paragraph_text(paragraphs: list) -> str:
        """
        Join non-empty paragraph text with newline separators.
        """
        return "\n".join(
            paragraph.text.strip()
            for paragraph in paragraphs
            if paragraph.text and paragraph.text.strip()
        )