"""
Table extraction service for Stage 2.

This service identifies markdown table blocks using deterministic heuristics:
- header row with pipes
- separator row containing dashes / colons
- one or more subsequent pipe-style rows
"""

from __future__ import annotations

import re

from backend.modules.ingestion.contracts.stage_2_contracts import (
    TableRecord,
    TableRegistry,
)


class TableExtractionService:
    """Extract markdown table blocks from parsed markdown."""

    _SEPARATOR_PATTERN = re.compile(r"^\s*\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")

    def extract_tables(self, markdown_text: str) -> TableRegistry:
        """Extract markdown tables and return a deterministic registry."""
        lines = markdown_text.splitlines()
        tables: list[TableRecord] = []

        index = 0
        table_counter = 1

        while index < len(lines) - 1:
            header_line = lines[index]
            separator_line = lines[index + 1]

            if self._looks_like_table_header(header_line) and self._SEPARATOR_PATTERN.match(separator_line):
                start_line = index + 1
                collected_lines = [header_line, separator_line]
                index += 2

                while index < len(lines) and self._looks_like_table_row(lines[index]):
                    collected_lines.append(lines[index])
                    index += 1

                table_markdown = "\n".join(collected_lines)
                header_columns = self._count_columns(header_line)
                data_row_count = max(0, len(collected_lines) - 2)

                tables.append(
                    TableRecord(
                        table_id=f"table_{table_counter:03d}",
                        markdown=table_markdown,
                        start_line=start_line,
                        end_line=start_line + len(collected_lines) - 1,
                        row_count=data_row_count,
                        column_count=header_columns,
                    )
                )
                table_counter += 1
                continue

            index += 1

        return TableRegistry(tables=tables)

    @staticmethod
    def _looks_like_table_header(line: str) -> bool:
        return "|" in line and len([cell for cell in line.split("|") if cell.strip()]) >= 2

    @staticmethod
    def _looks_like_table_row(line: str) -> bool:
        return "|" in line and bool(line.strip())

    @staticmethod
    def _count_columns(line: str) -> int:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        return len([cell for cell in cells if cell or cell == ""])