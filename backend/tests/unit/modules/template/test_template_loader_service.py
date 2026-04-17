"""
Tests for TemplateLoaderService.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.modules.template.repositories.template_repository import TemplateRepository
from backend.modules.template.services.template_loader_service import TemplateLoaderService
from backend.modules.template.models.template_enums import TemplateType
from backend.modules.template.contracts.template_contracts import TemplateDefinition, TemplateMetadata


@pytest.fixture
def repo(tmp_path: Path) -> TemplateRepository:
    std_dir = tmp_path / "standard"
    cus_dir = tmp_path / "custom"
    
    std_dir.mkdir(parents=True, exist_ok=True)
    file_path = std_dir / "standard_test.json"
    file_path.write_text(json.dumps({
        "metadata": {
            "template_id": "standard_test",
            "version": "1.0",
            "name": "Standard Mock",
            "template_type": "standard",
        },
        "sections": [{
            "section_id": "A",
            "title": "A",
            "generation_strategy": "summarize_text",
            "prompt": {"prompt_key": "x", "slots_required": ["source_evidence"]}
        }]
    }))
    
    return TemplateRepository(
        standard_templates_dir=std_dir,
        custom_templates_dir=cus_dir,
    )


@pytest.fixture
def loader(repo: TemplateRepository) -> TemplateLoaderService:
    return TemplateLoaderService(repository=repo)


def test_load_standard_template(loader: TemplateLoaderService):
    bundle = loader.load_template(
        template_type=TemplateType.STANDARD,
        template_id="standard_test",
    )
    assert bundle.template_type == TemplateType.STANDARD
    assert bundle.template_definition.metadata.template_id == "standard_test"


def test_load_standard_template_not_found(loader: TemplateLoaderService):
    with pytest.raises(FileNotFoundError):
        loader.load_template(
            template_type=TemplateType.STANDARD,
            template_id="missing_template",
        )


def test_load_custom_template_missing_version(loader: TemplateLoaderService):
    with pytest.raises(ValueError, match="`version` is required"):
        loader.load_template(
            template_type=TemplateType.CUSTOM,
            template_id="custom_template",
            # version explicitly missing
        )
