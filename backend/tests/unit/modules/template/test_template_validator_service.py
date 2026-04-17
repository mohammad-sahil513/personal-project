"""
Tests for TemplateValidatorService.
"""

from __future__ import annotations

import pytest

from backend.modules.template.contracts.section_contracts import (
    TemplateSection,
    RetrievalBinding,
)
from backend.modules.template.contracts.template_contracts import TemplateDefinition, TemplateMetadata, PromptReference
from backend.modules.template.models.template_enums import (
    GenerationStrategy,
    TemplateType,
    TemplateValidationCode,
)
from backend.modules.template.services.template_validator_service import TemplateValidatorService


def _create_template(section: TemplateSection) -> TemplateDefinition:
    return TemplateDefinition(
        metadata=TemplateMetadata(template_id="test", version="1", name="Test", template_type=TemplateType.STANDARD),
        sections=[section],
    )


def test_template_validation_valid():
    validator = TemplateValidatorService()
    section = TemplateSection(
        section_id="A",
        title="A",
        generation_strategy=GenerationStrategy.SUMMARIZE_TEXT,
        prompt=PromptReference(prompt_key="default", slots_required=["source_evidence"]),
        dependencies=[],
        retrieval=RetrievalBinding(
            profile_name="default",
            filters={"chunk_id": "react"}
        )
    )
    template = _create_template(section)
    
    result = validator.validate_template(template)
    assert result.is_valid is True
    assert result.error_count == 0
    assert result.warning_count == 0


def test_template_validation_missing_dependency():
    validator = TemplateValidatorService()
    section = TemplateSection(
        section_id="A",
        title="A",
        generation_strategy=GenerationStrategy.SUMMARIZE_TEXT,
        prompt=PromptReference(prompt_key="default", slots_required=["source_evidence"]),
        dependencies=["MISSING"],
    )
    template = _create_template(section)
    
    result = validator.validate_template(template)
    assert result.is_valid is False
    assert result.error_count == 1
    assert result.issues[0].code == TemplateValidationCode.INVALID_DEPENDENCY


def test_template_validation_unimplemented_strategy():
    validator = TemplateValidatorService()
    section = TemplateSection(
        section_id="A",
        title="A",
        generation_strategy=GenerationStrategy.DIAGRAM_PLANTUML,
        prompt=PromptReference(prompt_key="default", slots_required=["source_evidence"]),
        dependencies=[],
    )
    template = _create_template(section)
    
    result = validator.validate_template(template)
    assert result.is_valid is True # Warnings do not block
    assert result.warning_count == 1
    assert result.issues[0].code == TemplateValidationCode.UNIMPLEMENTED_STRATEGY


def test_template_validation_invalid_filter_key():
    validator = TemplateValidatorService()
    section = TemplateSection(
        section_id="A",
        title="A",
        generation_strategy=GenerationStrategy.SUMMARIZE_TEXT,
        prompt=PromptReference(prompt_key="default", slots_required=["source_evidence"]),
        dependencies=[],
        retrieval=RetrievalBinding(
            profile_name="default",
            filters={"fake_bad_filter": "yes"}
        )
    )
    template = _create_template(section)
    
    result = validator.validate_template(template)
    assert result.is_valid is False
    assert result.error_count == 1
    assert result.issues[0].code == TemplateValidationCode.INVALID_FILTER_KEY
