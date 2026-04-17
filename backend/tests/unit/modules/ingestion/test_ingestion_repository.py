import pytest
import os
from backend.modules.ingestion.repositories.ingestion_repository import IngestionRepository
from backend.modules.ingestion.contracts.stage_1_contracts import (
    IngestionJobRecord, IngestionJobStatus, IngestionStageName, StageExecutionStatus, BlobArtifactReference, StageStatusRecord
)
from datetime import datetime, UTC

@pytest.fixture
def repo(tmp_path):
    return IngestionRepository(base_dir=tmp_path)


@pytest.mark.asyncio
async def test_repo_initialization(repo, tmp_path):
    await repo.initialize()
    assert (tmp_path / "jobs").exists()
    assert (tmp_path / "hash_registry.json").exists()


@pytest.mark.asyncio
async def test_create_and_get_job(repo):
    record = IngestionJobRecord(
        process_id="p1",
        document_id="d1",
        file_name="f.pdf",
        content_type="application/pdf",
        sha256_hash="a"*64,
        source_blob=BlobArtifactReference(container_name="test", blob_path="sahil_storage/src", content_type="pdf", size_bytes=100),
        status=IngestionJobStatus.IN_PROGRESS,
        current_stage=IngestionStageName.UPLOAD_AND_DEDUP,
        is_duplicate=False,
        duplicate_of_document_id=None,
        initiated_by="user",
        correlation_id="corr",
        source_metadata={},
        stage_statuses={}
    )
    
    await repo.create_or_replace_job(record)
    
    fetched = await repo.get_job_by_document_id("d1")
    assert fetched is not None
    assert fetched.document_id == "d1"
    
    by_hash = await repo.get_job_by_sha256_hash("a"*64)
    assert by_hash is not None
    assert by_hash.document_id == "d1"


@pytest.mark.asyncio
async def test_update_stage_status(repo):
    record = IngestionJobRecord(
        process_id="p1",
        document_id="d1",
        file_name="f.pdf",
        content_type="application/pdf",
        sha256_hash="a"*64,
        source_blob=BlobArtifactReference(container_name="test", blob_path="sahil_storage/src", content_type="pdf", size_bytes=100),
        status=IngestionJobStatus.IN_PROGRESS,
        current_stage=IngestionStageName.UPLOAD_AND_DEDUP,
        is_duplicate=False,
        duplicate_of_document_id=None,
        initiated_by="user",
        correlation_id="corr",
        source_metadata={},
        stage_statuses={}
    )
    
    await repo.create_or_replace_job(record)
    
    now = datetime.now(UTC)
    updated = await repo.update_stage_status(
        document_id="d1",
        stage_name=IngestionStageName.PARSE_DOCUMENT,
        status=StageExecutionStatus.FAILED,
        warnings=[],
        details={"error": "failed parse"},
        started_at=now,
        completed_at=now
    )
    
    assert updated.current_stage == IngestionStageName.PARSE_DOCUMENT
    assert updated.stage_statuses[IngestionStageName.PARSE_DOCUMENT.value].status == StageExecutionStatus.FAILED


@pytest.mark.asyncio
async def test_mark_job_completed(repo):
    record = IngestionJobRecord(
        process_id="p1",
        document_id="d1",
        file_name="f.pdf",
        content_type="application/pdf",
        sha256_hash="a"*64,
        source_blob=BlobArtifactReference(container_name="test", blob_path="sahil_storage/src", content_type="pdf", size_bytes=100),
        status=IngestionJobStatus.IN_PROGRESS,
        current_stage=IngestionStageName.UPLOAD_AND_DEDUP,
        is_duplicate=False,
        duplicate_of_document_id=None,
        initiated_by="user",
        correlation_id="corr",
        source_metadata={},
        stage_statuses={}
    )
    
    await repo.create_or_replace_job(record)
    await repo.mark_job_completed(document_id="d1")
    
    fetched = await repo.get_job_by_document_id("d1")
    assert fetched.status == IngestionJobStatus.COMPLETED
