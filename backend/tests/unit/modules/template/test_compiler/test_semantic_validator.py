"""
Tests for SemanticValidator applying post-compile compiler rules.
"""

from __future__ import annotations

from backend.modules.template.compiler.semantic_validator import SemanticValidator
from backend.modules.template.contracts.template_contracts import TemplateDefinition, TemplateMetadata, PromptReference
from backend.modules.template.contracts.section_contracts import TemplateSection
from backend.modules.template.models.template_enums import GenerationStrategy, TemplateType


def test_semantic_validator_rules():
    validator = SemanticValidator()
    
    section = TemplateSection(
        section_id="A",
        title="A",
        # Invalid compiler rule
        generation_strategy=GenerationStrategy.DIAGRAM_PLANTUML,
        prompt=PromptReference(prompt_key="default", slots_required=["source_evidence"]),
        dependencies=[],
        # Missing retrieval causes SemanticValidation Error in custom templates
        retrieval=None 
    )
    
    template = TemplateDefinition(
        metadata=TemplateMetadata(
            template_id="custom_tpl",
            version="1.0",
            name="Custom",
            template_type=TemplateType.CUSTOM,
        ),
        sections=[section]
    )
    
    result = validator.validate_compiled_template(template)
    
    assert result.is_valid is False
    # Expect error for missing retrieval + error for auto-assigned plantuml
    assert len(result.errors) >= 2
    
    error_texts = str(result.errors)
    assert "missing a retrieval binding" in error_texts
    assert "auto-assigned `diagram_plantuml`" in error_texts
