"""
Tests for HeaderNormalizer formatting logic.
"""

from __future__ import annotations

from backend.modules.template.compiler.header_normalizer import HeaderNormalizer


def test_header_normalizer():
    normalizer = HeaderNormalizer()
    
    assert normalizer.normalize("Executive Summary!") == "executive summary"
    assert normalizer.normalize("  1.2.3   Architecture Overview ") == "architecture overview"
    assert normalizer.normalize("Non/Alphanumeric...Values") == "non alphanumeric values"
    assert normalizer.normalize("     ") == ""
