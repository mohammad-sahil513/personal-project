"""
Heading normalizer for custom template compilation.

Purpose:
- remove numbering prefixes,
- normalize punctuation/spacing,
- produce stable lowercase strings for deterministic matching.
"""

from __future__ import annotations

import re
import unicodedata


class HeaderNormalizer:
    """Normalize heading text into a deterministic matching form."""

    _LEADING_NUMBERING_PATTERN = re.compile(
        r"^\s*(?:section\s+)?(?:\d+(?:\.\d+)*)[\)\.\-:]?\s+",
        re.IGNORECASE,
    )
    _WHITESPACE_PATTERN = re.compile(r"\s+")
    _NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9\s]+")

    def normalize(self, text: str) -> str:
        """
        Normalize heading text for heuristic matching.

        Steps:
        1. Unicode normalize,
        2. lowercase,
        3. strip leading numbering,
        4. replace punctuation with spaces,
        5. collapse whitespace.
        """
        normalized = unicodedata.normalize("NFKC", text).strip().lower()
        normalized = self._LEADING_NUMBERING_PATTERN.sub("", normalized)
        normalized = normalized.replace("&", " and ")
        normalized = normalized.replace("/", " ")
        normalized = normalized.replace("_", " ")
        normalized = normalized.replace("-", " ")
        normalized = self._NON_ALNUM_PATTERN.sub(" ", normalized)
        normalized = self._WHITESPACE_PATTERN.sub(" ", normalized).strip()
        return normalized

    def slugify(self, text: str) -> str:
        """
        Convert heading text into a deterministic slug suitable for IDs/keys.
        """
        normalized = self.normalize(text)
        return normalized.replace(" ", "_")