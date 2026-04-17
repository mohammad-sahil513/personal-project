"""
Style parser for custom DOCX layout extraction.

This parser records a simplified style catalog so later rendering can prefer
named styles before falling back to direct formatting.

Compatibility note:
- python-docx may expose multiple style object variants inside `document.styles`.
- Some of those variants (for example certain numbering-related styles) do not
  expose the full attribute set used by paragraph/character/table styles.
- This parser therefore uses defensive attribute access instead of assuming
  every style object has `.base_style`, `.builtin`, etc.
"""

from __future__ import annotations

from docx.document import Document as DocxDocument

from .layout_contracts import StyleDefinition


class StyleParser:
    """Extract a simplified style map from a DOCX document."""

    def parse(self, document: DocxDocument) -> list[StyleDefinition]:
        """
        Parse document styles into lightweight style metadata.

        Defensive behavior:
        - skip styles with no usable name,
        - tolerate style objects that do not expose `.base_style`,
        - tolerate style objects with unusual type representations.
        """
        styles: list[StyleDefinition] = []

        for style in document.styles:
            style_name = getattr(style, "name", None)
            if not isinstance(style_name, str) or not style_name.strip():
                continue

            base_style_obj = getattr(style, "base_style", None)
            base_style_name = (
                getattr(base_style_obj, "name", None)
                if base_style_obj is not None
                else None
            )

            style_type_obj = getattr(style, "type", None)
            if style_type_obj is None:
                style_type = "UNKNOWN"
            else:
                style_type = getattr(style_type_obj, "name", str(style_type_obj))

            builtin = bool(getattr(style, "builtin", False))

            styles.append(
                StyleDefinition(
                    name=style_name,
                    style_type=style_type,
                    base_style_name=base_style_name,
                    builtin=builtin,
                )
            )

        styles.sort(key=lambda item: (item.style_type, item.name.lower()))
        return styles