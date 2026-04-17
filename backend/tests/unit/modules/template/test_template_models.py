"""
Tests for Template Config Models and Enums.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.modules.template.models.template_enums import (
    GenerationStrategy,
    TemplateType,
    ValidationSeverity,
)
from backend.modules.template.contracts.template_contracts import TemplateMetadata


def test_template_enums():
    assert GenerationStrategy.SUMMARIZE_TEXT == "summarize_text"
    assert TemplateType.CUSTOM == "custom"
    assert ValidationSeverity.ERROR == "error"


def test_template_metadata_valid():
    meta = TemplateMetadata(
        template_id="tpl_1",
        version="1.0.0",
        name="Test Template",
        template_type=TemplateType.STANDARD,
    )
    assert meta.template_id == "tpl_1"
    assert meta.template_type == TemplateType.STANDARD


def test_template_metadata_invalid():
    # Test missing required field (id)
    with pytest.raises(ValidationError):
        TemplateMetadata(
            name="Test Template",
            version="1.0.0",
            template_type=TemplateType.STANDARD,
        )
