"""
Tests for DefaultsInjector mutating placeholder configurations.
"""

from __future__ import annotations

from backend.modules.template.compiler.defaults_injector import DefaultsInjector, CompiledSectionSeed
from backend.modules.template.contracts.compiler_contracts import ExtractedHeading
from backend.modules.template.models.template_enums import GenerationStrategy, TemplateType


def test_defaults_injector_logic():
    injector = DefaultsInjector()
    
    seed = CompiledSectionSeed(
        heading=ExtractedHeading(
            raw_text="System Architecture",
            normalized_text="system_architecture",
            level=1,
            order_index=0,
        ),
        selected_section_id=None,
        selected_title=None,
        confidence=None,
    )
    
    template, result = injector.inject_defaults(
        template_id="tpl",
        name="Test",
        version="1.0",
        section_seeds=[seed],
    )
    
    assert len(template.sections) == 1
    assert template.sections[0].generation_strategy is not None
    assert template.sections[0].retrieval is not None
    assert template.default_grounding_policy is not None
