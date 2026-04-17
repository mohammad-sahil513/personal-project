"""
Tests for Template Contracts constraints.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.modules.template.contracts.template_contracts import TemplateDefinition, TemplateMetadata
from backend.modules.template.contracts.compiler_contracts import CompiledTemplateArtifact, CompilerArtifactReference
from backend.modules.template.contracts.section_contracts import TemplateSection
from backend.modules.template.models.template_enums import TemplateType, CompilerArtifactType


def test_template_definition():
    definition = TemplateDefinition(
        metadata=TemplateMetadata(
            template_id="tpl_A",
            version="v1",
            name="Test",
            template_type=TemplateType.STANDARD,
        ),
        sections=[TemplateSection.model_construct(section_id="A")],
    )
    assert definition.metadata.template_id == "tpl_A"


def test_compiled_artifact_paths():
    manifest = CompiledTemplateArtifact(
        template_id="custom_tpl",
        version="v2",
        template_json=CompilerArtifactReference(
            artifact_type=CompilerArtifactType.COMPILED_TEMPLATE_JSON,
            path="template.json",
            version="v2",
        ),
        layout_manifest=CompilerArtifactReference(
            artifact_type=CompilerArtifactType.LAYOUT_MANIFEST,
            path="layout.json",
            version="v2",
        ),
        shell_docx=CompilerArtifactReference(
            artifact_type=CompilerArtifactType.SHELL_DOCX,
            path="shell.docx",
            version="v2",
        ),
    )
    assert manifest.template_id == "custom_tpl"
    assert manifest.template_json.path == "template.json"
    

def test_compiled_artifact_validation_error():
    # Missing required artifact_type and version
    with pytest.raises(ValidationError):
        CompiledTemplateArtifact(
            template_id="custom_tpl",
            version="v2",
            template_json={"path": "template.json"},
            layout_manifest={"path": "layout.json"},
        )
