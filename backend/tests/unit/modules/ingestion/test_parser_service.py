import pytest
from backend.modules.ingestion.services.parser_service import ParserService, DocumentIntelligenceClientProtocol, BlobPersistenceClientProtocol
from backend.modules.ingestion.contracts.stage_1_contracts import BlobArtifactReference
from backend.modules.ingestion.contracts.stage_2_contracts import Stage2Input
from backend.modules.ingestion.exceptions import ParsingError

class MockDocIntelClient:
    async def analyze_to_markdown(self, *, source_blob: BlobArtifactReference) -> str:
        if source_blob.blob_path == "sahil_storage/fail":
            raise ValueError("Failure")
        if source_blob.blob_path == "sahil_storage/empty":
            return "   "
        return "# Heading 1\n\nSome text with an email test@example.com\n\n## Subheading\n\nMore text."

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
def parser_service():
    return ParserService(
        document_intelligence_client=MockDocIntelClient(),
        blob_client=MockBlobClient(),
        blob_container_name="test-container"
    )

@pytest.mark.asyncio
async def test_parse_valid_document(parser_service):
    req = Stage2Input(
        process_id="proc",
        document_id="doc",
        sha256_hash="a"*64,
        source_blob=BlobArtifactReference(container_name="test", blob_path="sahil_storage/valid", content_type="application/pdf", size_bytes=100),
        prior_warnings=[],
        file_name="test.pdf",
        content_type="application/pdf"
    )
    
    out = await parser_service.parse_document(req)
    assert "Heading 1" in out.raw_markdown
    assert out.parse_quality_report.heading_count > 0
    assert out.parse_quality_report.estimated_tokens > 0

@pytest.mark.asyncio
async def test_parse_empty_output(parser_service):
    req = Stage2Input(
        process_id="proc",
        document_id="doc",
        sha256_hash="a"*64,
        source_blob=BlobArtifactReference(container_name="test", blob_path="sahil_storage/empty", content_type="application/pdf", size_bytes=100),
        prior_warnings=[],
        file_name="empty.pdf",
        content_type="application/pdf"
    )
    
    with pytest.raises(ParsingError) as exc:
        await parser_service.parse_document(req)
    assert "produced empty markdown output" in str(exc.value)
