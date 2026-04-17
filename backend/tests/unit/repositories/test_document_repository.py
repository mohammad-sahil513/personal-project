"""
Tests for DocumentRepository, covering standard CRUD, binaries, and edge cases.
"""

from __future__ import annotations

import concurrent.futures
from pathlib import Path

import pytest
from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.repositories.document_repository import DocumentRepository


@pytest.fixture
def repo(tmp_storage: Path, settings_override) -> DocumentRepository:
    return DocumentRepository()


def test_document_crud_happy_path(repo: DocumentRepository):
    # Create
    record = {"document_id": "doc_123", "name": "test.txt", "size": 100}
    repo.create(record)

    # Get
    fetched = repo.get("doc_123")
    assert fetched == record

    # Update
    repo.update("doc_123", {"size": 200})
    updated = repo.get("doc_123")
    assert updated["size"] == 200

    # List
    items = repo.list()
    assert len(items) == 1
    assert items[0]["document_id"] == "doc_123"

    # Delete
    repo.delete("doc_123")
    with pytest.raises(NotFoundError):
        repo.get("doc_123")


def test_document_binary_lifecycle(repo: DocumentRepository):
    # Save
    data = b"hello binary world"
    repo.save_binary("doc_bin_1", data)

    # Get
    fetched = repo.get_binary("doc_bin_1")
    assert fetched == data

    # Delete (repository delete should also cleanup the .bin if exists)
    repo.create({"document_id": "doc_bin_1", "status": "stored"})
    repo.delete("doc_bin_1")
    with pytest.raises(NotFoundError):
        repo.get_binary("doc_bin_1")


def test_document_errors(repo: DocumentRepository):
    # Create without ID
    with pytest.raises(ValidationError, match="document_id is required"):
        repo.create({"name": "no_id"})

    # Duplicate create
    repo.create({"document_id": "dup_1"})
    with pytest.raises(ConflictError, match="already exists"):
        repo.create({"document_id": "dup_1"})

    # Get non-existent
    with pytest.raises(NotFoundError):
        repo.get("missing")

    # Update non-existent
    with pytest.raises(NotFoundError):
        repo.update("missing", {"foo": "bar"})

    # Delete non-existent
    with pytest.raises(NotFoundError):
        repo.delete("missing")
        
    # Get binary non-existent
    with pytest.raises(NotFoundError):
        repo.get_binary("missing")


def test_document_large_payload(repo: DocumentRepository):
    large_list = ["a" * 100] * 10000  # ~1MB payload
    record = {"document_id": "large_1", "data": large_list}
    repo.create(record)
    
    fetched = repo.get("large_1")
    assert len(fetched["data"]) == 10000


def test_document_concurrent_writes(repo: DocumentRepository):
    # While file systems aren't perfectly transactional via standard python open(),
    # writing unique files should be thread-safe enough for non-conflicting IDs.
    
    def construct_and_save(i: int):
        doc_id = f"conc_{i}"
        repo.create({"document_id": doc_id, "val": i})
        return repo.get(doc_id)["val"]
        
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(construct_and_save, i) for i in range(50)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
    assert len(results) == 50
    assert len(repo.list()) == 50
