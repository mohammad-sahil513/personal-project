"""
Tests for TemplateMetadataRepository, covering CRUD, binaries, and edge cases.
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

import pytest
from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.repositories.template_metadata_repository import TemplateMetadataRepository


@pytest.fixture
def repo(tmp_storage: Path, settings_override) -> TemplateMetadataRepository:
    return TemplateMetadataRepository()


def test_template_crud_happy_path(repo: TemplateMetadataRepository):
    record = {"template_id": "tpl_123", "name": "Spec", "author": "John"}
    repo.create(record)

    fetched = repo.get("tpl_123")
    assert fetched == record

    repo.update("tpl_123", {"author": "Jane"})
    assert repo.get("tpl_123")["author"] == "Jane"

    items = repo.list()
    assert len(items) == 1
    assert items[0]["template_id"] == "tpl_123"

    repo.delete("tpl_123")
    with pytest.raises(NotFoundError):
        repo.get("tpl_123")


def test_template_binary_lifecycle(repo: TemplateMetadataRepository):
    data = b"docx binary content mock"
    repo.save_binary("tpl_bin_1", data)

    fetched = repo.get_binary("tpl_bin_1")
    assert fetched == data

    repo.create({"template_id": "tpl_bin_1", "status": "stored"})
    repo.delete("tpl_bin_1")
    with pytest.raises(NotFoundError):
        repo.get_binary("tpl_bin_1")


def test_template_errors(repo: TemplateMetadataRepository):
    # Create with None ID explicitly
    with pytest.raises(ValidationError, match="template_id is required"):
        repo.create({"template_id": None, "name": "no_id"})

    # Duplicate
    repo.create({"template_id": "dup_1"})
    with pytest.raises(ConflictError):
        repo.create({"template_id": "dup_1"})

    # Missing
    with pytest.raises(NotFoundError):
        repo.get("missing")


def test_template_large_payload(repo: TemplateMetadataRepository):
    # A massive dependency array
    large_deps = [{"source": "a", "target": "b"}] * 15000
    repo.create({"template_id": "tpl_large", "deps": large_deps})
    assert len(repo.get("tpl_large")["deps"]) == 15000


def test_template_concurrent_writes(repo: TemplateMetadataRepository):
    def save(i: int):
        doc_id = f"tpl_conc_{i}"
        repo.create({"template_id": doc_id})
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(save, i) for i in range(20)]
        concurrent.futures.wait(futures)
        
    assert len(repo.list()) == 20
