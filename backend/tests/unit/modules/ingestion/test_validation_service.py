import pytest
from backend.modules.ingestion.services.validation_service import ValidationService
from backend.modules.ingestion.contracts.stage_7_contracts import Stage7Input, ValidationSeverity, ValidationIssueCode
from backend.modules.ingestion.contracts.stage_1_contracts import BlobArtifactReference
from backend.modules.ingestion.contracts.stage_6_contracts import SegmentedSection, StructuralSignals, SectionType
from backend.modules.ingestion.contracts.stage_2_contracts import AssetRegistry, ParseQualityReport, ParseQualityTier


def test_validation_service_success():
    service = ValidationService()
    
    req = Stage7Input(
        process_id="proc",
        document_id="doc",
        source_blob=BlobArtifactReference(container_name="test", blob_path="sahil_storage/p", content_type="t", size_bytes=1),
        sections=[
            SegmentedSection(
                section_id="sec_1",
                heading="Test",
                heading_level=1,
                section_index=1,
                section_type=SectionType.OVERVIEW,
                raw_content="Valid content.",
                preview_text="Preview",
                structural_signals=StructuralSignals(
                    has_table=False, has_list=False, has_requirement_pattern=False, has_asset_reference=False, has_h3_subheading=False, estimated_tokens=10
                ),
                warnings=[]
            )
        ],
        asset_registry=AssetRegistry(assets=[]),
        parse_quality_report=ParseQualityReport(heading_count=1, image_count=0, table_count=0, hyperlink_count=0, estimated_tokens=10, quality_tier=ParseQualityTier.GOOD, embedded_object_detected=False, warnings=[]),
        enriched_markdown_artifact=BlobArtifactReference(container_name="test", blob_path="sahil_storage/p", content_type="t", size_bytes=1),
        pii_enabled=False,
        allowlisted_system_emails=[],
        mapped_pii_values=[],
        prior_warnings=[],
    )
    
    out = service.validate(req)
    assert out.summary.has_global_failure is False
    assert out.summary.can_proceed_to_chunking is True
    assert out.summary.error_count == 0


def test_validation_service_empty_markdown():
    service = ValidationService()
    
    req = Stage7Input(
        process_id="proc",
        document_id="doc",
        source_blob=BlobArtifactReference(container_name="test", blob_path="sahil_storage/p", content_type="t", size_bytes=1),
        sections=[
            SegmentedSection(
                section_id="sec_1",
                heading="Test",
                heading_level=1,
                section_index=1,
                section_type=SectionType.OVERVIEW,
                raw_content="Valid content.",
                preview_text="Preview",
                structural_signals=StructuralSignals(
                    has_table=False, has_list=False, has_requirement_pattern=False, has_asset_reference=False, has_h3_subheading=False, estimated_tokens=10
                ),
                warnings=[]
            )
        ],
        asset_registry=AssetRegistry(assets=[]),
        parse_quality_report=ParseQualityReport(heading_count=0, image_count=0, table_count=0, hyperlink_count=0, estimated_tokens=0, quality_tier=ParseQualityTier.DEGRADED, embedded_object_detected=False, warnings=[]),
        enriched_markdown_artifact=BlobArtifactReference(container_name="test", blob_path="sahil_storage/p", content_type="t", size_bytes=1),
        pii_enabled=False,
        allowlisted_system_emails=[],
        mapped_pii_values=[],
        prior_warnings=[],
    )
    
    out = service.validate(req)
    assert out.summary.has_global_failure is True
    assert out.summary.can_proceed_to_chunking is False
    assert out.summary.error_count > 0
    assert any(issue.code == ValidationIssueCode.EMPTY_MARKDOWN for issue in out.issues)
