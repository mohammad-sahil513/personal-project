import pytest
from backend.modules.ingestion.services.pii_service import PiiService, RegexPiiCandidateDetector, RuleBasedPiiClassifier, BlobPersistenceClientProtocol
from backend.modules.ingestion.contracts.stage_1_contracts import BlobArtifactReference
from backend.modules.ingestion.contracts.stage_2_contracts import AssetRegistry, TableRegistry, ParseQualityReport, ParseQualityTier, HyperlinkRegistry
from backend.modules.ingestion.contracts.stage_3_contracts import Stage3Input, PiiDecisionAction, PiiEntityType

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
def pii_service():
    return PiiService(
        candidate_detector=RegexPiiCandidateDetector(),
        classifier=RuleBasedPiiClassifier(),
        blob_client=MockBlobClient(),
        blob_container_name="test-container"
    )

@pytest.mark.asyncio
async def test_pii_disabled(pii_service):
    req = Stage3Input(
        process_id="proc",
        document_id="doc",
        source_blob=BlobArtifactReference(container_name="test", blob_path="sahil_storage/valid", content_type="application/pdf", size_bytes=100),
        enriched_markdown="test@example.com",
        enriched_markdown_artifact=BlobArtifactReference(container_name="test", blob_path="sahil_storage/enrich", content_type="md", size_bytes=1),
        asset_registry=AssetRegistry(assets=[]),
        hyperlink_registry=HyperlinkRegistry(hyperlinks=[]),
        table_registry=TableRegistry(tables=[]),
        parse_quality_report=ParseQualityReport(heading_count=1, image_count=0, table_count=0, hyperlink_count=0, estimated_tokens=10, quality_tier=ParseQualityTier.GOOD, embedded_object_detected=False, warnings=[]),
        prior_warnings=[],
        pii_enabled=False,
        system_email_allowlist=[]
    )
    
    out = await pii_service.process_pii(req)
    assert out.masked_markdown == "test@example.com"
    assert out.metrics.total_candidates_detected == 0

@pytest.mark.asyncio
async def test_pii_enabled_detection_and_masking(pii_service):
    req = Stage3Input(
        process_id="proc",
        document_id="doc",
        source_blob=BlobArtifactReference(container_name="test", blob_path="sahil_storage/valid", content_type="application/pdf", size_bytes=100),
        enriched_markdown="Contact us at person@example.com or support@example.com.",
        enriched_markdown_artifact=BlobArtifactReference(container_name="test", blob_path="sahil_storage/enrich", content_type="md", size_bytes=1),
        asset_registry=AssetRegistry(assets=[]),
        hyperlink_registry=HyperlinkRegistry(hyperlinks=[]),
        table_registry=TableRegistry(tables=[]),
        parse_quality_report=ParseQualityReport(heading_count=1, image_count=0, table_count=0, hyperlink_count=0, estimated_tokens=10, quality_tier=ParseQualityTier.GOOD, embedded_object_detected=False, warnings=[]),
        prior_warnings=[],
        pii_enabled=True,
        system_email_allowlist=["support@example.com"]
    )
    
    out = await pii_service.process_pii(req)
    assert out.metrics.total_candidates_detected == 2
    assert out.metrics.total_candidates_masked == 1
    assert out.metrics.total_candidates_kept == 1
    
    assert "[PII_EMAIL_001]" in out.masked_markdown
    assert "person@example.com" not in out.masked_markdown
    assert "support@example.com" in out.masked_markdown  # Kept!
