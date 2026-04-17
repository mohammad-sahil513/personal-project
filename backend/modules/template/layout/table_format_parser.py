"""
Table format parser for custom DOCX layout extraction.

This parser captures lightweight table metadata so later rendering can preserve
table structure/style expectations without reparsing the original source file.
"""

from __future__ import annotations

from docx.document import Document as DocxDocument

from .layout_contracts import TableFormatInfo


class TableFormatParser:
    """Extract simplified table metadata from a DOCX document."""

    def parse(self, document: DocxDocument) -> list[TableFormatInfo]:
        """
        Parse all tables into lightweight formatting metadata.
        """
        tables: list[TableFormatInfo] = []

        for table_index, table in enumerate(document.tables):
            row_count = len(table.rows)
            column_count = max((len(row.cells) for row in table.rows), default=0)
            style_name = table.style.name if table.style is not None else None

            tables.append(
                TableFormatInfo(
                    table_index=table_index,
                    row_count=row_count,
                    column_count=column_count,
                    style_name=style_name,
                )
            )

        return tables