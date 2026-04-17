"""
Tests for ExecutionRepository.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.core.exceptions import ConflictError, NotFoundError, ValidationError
from backend.repositories.execution_repository import ExecutionRepository


@pytest.fixture
def repo(tmp_storage: Path, settings_override) -> ExecutionRepository:
    return ExecutionRepository()


def test_execution_crud(repo: ExecutionRepository):
    record = {"execution_id": "ex_1", "task": "chunking"}
    repo.create(record)

    fetched = repo.get("ex_1")
    assert fetched == record

    repo.update("ex_1", {"task": "indexing"})
    assert repo.get("ex_1")["task"] == "indexing"

    assert len(repo.list()) == 1

    repo.delete("ex_1")
    with pytest.raises(NotFoundError):
        repo.get("ex_1")


def test_execution_errors(repo: ExecutionRepository):
    with pytest.raises(ValidationError):
        repo.create({"no": "id"})

    repo.create({"execution_id": "ex_2"})
    with pytest.raises(ConflictError):
        repo.create({"execution_id": "ex_2"})

    with pytest.raises(NotFoundError):
        repo.get("missing")
