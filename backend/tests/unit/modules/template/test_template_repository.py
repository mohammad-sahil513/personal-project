"""
Tests for TemplateRepository (Artifact filesystem).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.modules.template.repositories.template_repository import TemplateRepository
from backend.modules.template.contracts.template_contracts import TemplateDefinition, TemplateMetadata, PromptReference
from backend.modules.template.contracts.compiler_contracts import CompiledTemplateArtifact, CompilerArtifactReference
from backend.modules.template.contracts.section_contracts import TemplateSection
from backend.modules.template.models.template_enums import TemplateType, CompilerArtifactType, GenerationStrategy


@pytest.fixture
def repo(tmp_path: Path) -> TemplateRepository:
    std_dir = tmp_path / "standard"
    cus_dir = tmp_path / "custom"
    return TemplateRepository(
        standard_templates_dir=std_dir,
        custom_templates_dir=cus_dir,
    )


def test_standard_template_load(repo: TemplateRepository, tmp_path: Path):
    std_dir = tmp_path / "standard"
    std_dir.mkdir(parents=True, exist_ok=True)
    
    # Write mock JSON
    file_path = std_dir / "pdd_v1.json"
    file_path.write_text(json.dumps({
        "metadata": {
            "template_id": "pdd_v1",
            "version": "1.0",
            "name": "PDD",
            "template_type": "standard"
        },
        "sections": [{
            "section_id": "A",
            "title": "A",
            "generation_strategy": "summarize_text",
            "prompt": {"prompt_key": "x", "slots_required": ["source_evidence"]}
        }]
    }))
    
    definition = repo.load_standard_template("pdd_v1")
    assert definition.metadata.template_id == "pdd_v1"
    

def test_custom_template_lifecycle(repo: TemplateRepository):
    definition = TemplateDefinition(
        metadata=TemplateMetadata(
            template_id="custom",
            version="1.1",
            name="Custom Doc",
            template_type=TemplateType.CUSTOM,
        ),
        sections=[TemplateSection(
            section_id="A",
            title="A",
            generation_strategy=GenerationStrategy.SUMMARIZE_TEXT,
            prompt=PromptReference(prompt_key="default", slots_required=["source_evidence"])
        )]
    )
    
    # Save Definition
    repo.save_custom_template_definition(
        template_definition=definition,
        template_id="custom",
        version="1.1"
    )
    
    artifact = CompiledTemplateArtifact(
        template_id="custom",
        version="1.1",
        template_json=CompilerArtifactReference(
            artifact_type=CompilerArtifactType.COMPILED_TEMPLATE_JSON,
            path="template.json",
            version="1.1",
        ),
        layout_manifest=CompilerArtifactReference(
            artifact_type=CompilerArtifactType.LAYOUT_MANIFEST,
            path="layout.json",
            version="1.1",
        ),
        shell_docx=CompilerArtifactReference(
            artifact_type=CompilerArtifactType.SHELL_DOCX,
            path="shell.docx",
            version="1.1",
        )
    )
    repo.save_compiled_template_artifact(artifact)
    
    # Load combined
    loaded_def, loaded_artifact, resolved_path = repo.load_custom_template_definition(
        template_id="custom",
        version="1.1"
    )
    
    assert loaded_def.metadata.name == "Custom Doc"
    assert loaded_artifact.shell_docx.path == "shell.docx"
    assert str(resolved_path).endswith("template.json")


def test_missing_files(repo: TemplateRepository):
    with pytest.raises(FileNotFoundError):
        repo.load_standard_template("missing")
        
    with pytest.raises(FileNotFoundError):
        repo.load_custom_template_definition(template_id="missing", version="1")
