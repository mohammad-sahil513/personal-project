"""
Tests for TemplateResolverService.
"""

from __future__ import annotations

import pytest

from backend.modules.template.contracts.section_contracts import (
    TemplateSection,
    RetrievalBinding,
)
from backend.modules.template.contracts.template_contracts import (
    TemplateDefinition,
    TemplateMetadata,
    PromptReference,
    GroundingPolicy,
)
from backend.modules.template.models.template_enums import GenerationStrategy, TemplateType
from backend.modules.template.services.template_resolver_service import TemplateResolverService


def test_template_resolver_merges_policies():
    resolver = TemplateResolverService()
    
    section = TemplateSection(
        section_id="A",
        title="A",
        generation_strategy=GenerationStrategy.SUMMARIZE_TEXT,
        prompt=PromptReference(prompt_key="default", slots_required=["source_evidence"]),
        dependencies=[],
        grounding_policy=GroundingPolicy(
            evidence_confidence_floor=0.9
        )
    )
    
    template = TemplateDefinition(
        metadata=TemplateMetadata(template_id="test", version="1", name="Test", template_type=TemplateType.STANDARD),
        default_grounding_policy=GroundingPolicy(
            evidence_confidence_floor=0.7,
            allow_inference=False,
        ),
        sections=[section],
    )
    
    resolved_sections = resolver.resolve_template(template)
    assert len(resolved_sections) == 1
    
    sec = resolved_sections[0]
    # Verify policy merged from fallback
    assert sec.grounding_policy is not None
    assert sec.grounding_policy.evidence_confidence_floor == 0.9 # overridden
    assert sec.grounding_policy.allow_inference is False         # inherited
