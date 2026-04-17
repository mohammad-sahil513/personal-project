import pytest
from backend.modules.ingestion.services.segmentation_service import SegmentationService
from backend.modules.ingestion.contracts.stage_6_contracts import Stage6Input
from backend.modules.ingestion.contracts.stage_1_contracts import BlobArtifactReference
from backend.modules.ingestion.contracts.stage_2_contracts import AssetRegistry, HyperlinkRegistry, TableRegistry, ParseQualityReport, ParseQualityTier

def test_segmentation_service():
    service = SegmentationService()
    markdown = "# Heading 1\n\nSome text.\n\n## Subheading\n\nMore text."
    
    req = Stage6Input(
        process_id="proc",
        document_id="doc",
        source_blob=BlobArtifactReference(container_name="test", blob_path="sahil_storage/p", content_type="t", size_bytes=1),
        enriched_markdown=markdown,
        enriched_markdown_artifact=BlobArtifactReference(container_name="test", blob_path="sahil_storage/p", content_type="t", size_bytes=1),
        asset_registry=AssetRegistry(),
        hyperlink_registry=HyperlinkRegistry(),
        table_registry=TableRegistry(),
        parse_quality_report=ParseQualityReport(heading_count=2, image_count=0, table_count=0, hyperlink_count=0, estimated_tokens=10, quality_tier=ParseQualityTier.GOOD),
        prior_warnings=[]
    )
    
    out = service.segment_document(req)
    assert len(out.sections) == 2
    assert out.sections[0].heading == "Heading 1"
    assert out.sections[1].heading == "Subheading"

def test_segmentation_no_headings():
    service = SegmentationService()
    markdown = "Just some plain text without headings."
    
    req = Stage6Input(
        process_id="proc",
        document_id="doc",
        source_blob=BlobArtifactReference(container_name="test", blob_path="sahil_storage/p", content_type="t", size_bytes=1),
        enriched_markdown=markdown,
        enriched_markdown_artifact=BlobArtifactReference(container_name="test", blob_path="sahil_storage/p", content_type="t", size_bytes=1),
        asset_registry=AssetRegistry(),
        hyperlink_registry=HyperlinkRegistry(),
        table_registry=TableRegistry(),
        parse_quality_report=ParseQualityReport(heading_count=0, image_count=0, table_count=0, hyperlink_count=0, estimated_tokens=10, quality_tier=ParseQualityTier.DEGRADED),
        prior_warnings=[]
    )
    
    out = service.segment_document(req)
    assert len(out.sections) == 1
    assert out.sections[0].heading == "Document Root"
