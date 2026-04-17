"""
Tests for OutputRepository.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from backend.core.exceptions import ConflictError, NotFoundError
from backend.repositories.output_repository import OutputRepository


@pytest.fixture
def repo(tmp_storage: Path, settings_override) -> OutputRepository:
    return OutputRepository()


def test_output_crud(repo: OutputRepository):
    # OutputRepository is slightly different, it uses record["output_id"] instead of .get()
    # It will throw KeyError if output_id isn't provided directly, which is expected API per implementation.
    record = {"output_id": "out_1", "content": "hello"}
    repo.create(record)

    fetched = repo.get("out_1")
    assert fetched == record

    repo.update("out_1", {"content": "world"})
    assert repo.get("out_1")["content"] == "world"

    # There is no delete() or list() in OutputRepository by default currently,
    # so we just test what it implements.


def test_output_errors(repo: OutputRepository):
    repo.create({"output_id": "out_2"})
    with pytest.raises(ConflictError):
        repo.create({"output_id": "out_2"})

    with pytest.raises(NotFoundError):
        repo.get("missing")
