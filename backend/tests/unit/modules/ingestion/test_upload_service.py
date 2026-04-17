import pytest
from backend.modules.ingestion.contracts.stage_1_contracts import Stage1Input, BlobArtifactReference, SupportedDocumentExtension
from backend.modules.ingestion.exceptions import UnsupportedDocumentTypeError
from backend.modules.ingestion.services.upload_service import UploadService, BlobStorageClientProtocol
from backend.modules.ingestion.repositories.ingestion_repository import IngestionRepository


class MockBlobClient:
    async def upload_bytes(
        self,
        *,
        container_name: str,
        blob_path: str,
        data: bytes,
        content_type: str,
        overwrite: bool = True,
    ) -> BlobArtifactReference:
        return BlobArtifactReference(
            container_name=container_name,
            blob_path=blob_path,
            content_type=content_type,
            size_bytes=len(data)
        )


@pytest.fixture
def mock_repo(tmp_path):
    repo = IngestionRepository(tmp_path)
    return repo


@pytest.fixture
def upload_service(mock_repo):
    return UploadService(
        blob_client=MockBlobClient(),
        repository=mock_repo,
        blob_container_name="test-container"
    )


@pytest.mark.asyncio
async def test_upload_and_deduplicate_valid(upload_service):
    request = Stage1Input(
        file_name="test.pdf",
        content_type="application/pdf",
        file_bytes=b"valid pdf data",
        initiated_by="tester",
        correlation_id="corr_1",
        source_metadata={}
    )
    
    output = await upload_service.upload_and_deduplicate(request)
    assert output.process_id is not None
    assert output.document_id is not None
    assert output.is_duplicate is False
    assert output.original_file.size_bytes == len(b"valid pdf data")


@pytest.mark.asyncio
async def test_upload_and_deduplicate_duplicate(upload_service, mock_repo):
    request1 = Stage1Input(
        file_name="test.pdf",
        content_type="application/pdf",
        file_bytes=b"dup data",
        initiated_by="tester",
        correlation_id="corr_1",
        source_metadata={}
    )
    
    # First upload
    out1 = await upload_service.upload_and_deduplicate(request1)
    
    # Second upload with same bytes
    request2 = Stage1Input(
        file_name="test2.pdf",
        content_type="application/pdf",
        file_bytes=b"dup data",
        initiated_by="tester",
        correlation_id="corr_2",
        source_metadata={}
    )
    
    out2 = await upload_service.upload_and_deduplicate(request2)
    assert out2.is_duplicate is True
    assert out2.duplicate_of_document_id == out1.document_id
    assert len(out2.warnings) == 1
    assert out2.warnings[0].code == "DUPLICATE_DOCUMENT_DETECTED"


@pytest.mark.asyncio
async def test_unsupported_file(upload_service):
    request = Stage1Input(
        file_name="test.txt",
        content_type="text/plain",
        file_bytes=b"text",
        initiated_by="tester",
        correlation_id="corr_1",
        source_metadata={}
    )
    
    with pytest.raises(UnsupportedDocumentTypeError) as exc:
        await upload_service.upload_and_deduplicate(request)
    assert "Only structured PDF and DOCX documents are supported" in str(exc.value)

@pytest.mark.asyncio
async def test_mismatched_content_type(upload_service):
    request = Stage1Input(
        file_name="test.pdf",
        content_type="text/plain",
        file_bytes=b"text",
        initiated_by="tester",
        correlation_id="corr_1",
        source_metadata={}
    )
    
    with pytest.raises(UnsupportedDocumentTypeError) as exc:
        await upload_service.upload_and_deduplicate(request)
    assert "content type does not match" in str(exc.value)
