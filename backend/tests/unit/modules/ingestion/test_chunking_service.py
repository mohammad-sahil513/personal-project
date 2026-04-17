import pytest
from backend.modules.ingestion.services.chunking_service import ChunkingService
from backend.modules.ingestion.contracts.stage_7_contracts import ValidationSummary
from backend.modules.ingestion.contracts.stage_6_contracts import SegmentedSection, StructuralSignals, SectionType
from backend.modules.ingestion.contracts.stage_8_contracts import Stage8Input
from backend.modules.ingestion.contracts.stage_1_contracts import BlobArtifactReference

def test_chunking_service_prose():
    service = ChunkingService()
    
    section = SegmentedSection(
        section_id="sec_1",
        heading="Test",
        heading_level=1,
        section_index=1,
        section_type=SectionType.OVERVIEW,
        raw_content="This is a test sentence. " * 200,  # about 200 sentences -> needs split
        preview_text="Preview",
        structural_signals=StructuralSignals(
            has_table=False, has_list=False, has_requirement_pattern=False, has_asset_reference=False, has_h3_subheading=False, estimated_tokens=1300
        ),
        warnings=[]
    )
    
    req = Stage8Input(
        process_id="proc",
        document_id="doc",
        source_blob=BlobArtifactReference(container_name="test", blob_path="sahil_storage/p", content_type="t", size_bytes=1),
        sections=[section],
        prior_warnings=[],
        validation_summary=ValidationSummary(total_issues=0, error_count=0, warning_count=0, has_global_failure=False, can_proceed_to_chunking=True)
    )
    
    out = service.chunk_document(req)
    assert out.metrics.total_chunks_created > 1
    assert all(chk.estimated_tokens <= 900 for chk in out.chunks)

def test_chunking_service_preserves_table():
    service = ChunkingService()
    table_content = "\n".join(["| header |", "|---|", *["| row |" for _ in range(800)]]) # massive table
    
    section = SegmentedSection(
        section_id="sec_1",
        heading="Test",
        heading_level=1,
        section_index=1,
        section_type=SectionType.OVERVIEW,
        raw_content="# Test Data\n\n" + table_content,
        preview_text="Preview",
        structural_signals=StructuralSignals(
            has_table=True, has_list=False, has_requirement_pattern=False, has_asset_reference=False, has_h3_subheading=False, estimated_tokens=1500
        ),
        warnings=[]
    )
    
    req = Stage8Input(
        process_id="proc",
        document_id="doc",
        source_blob=BlobArtifactReference(container_name="test", blob_path="sahil_storage/p", content_type="t", size_bytes=1),
        sections=[section],
        prior_warnings=[],
        validation_summary=ValidationSummary(total_issues=0, error_count=0, warning_count=0, has_global_failure=False, can_proceed_to_chunking=True)
    )
    
    out = service.chunk_document(req)
    # The table is kept as one block despite size
    assert out.metrics.total_chunks_created == 1
    assert out.chunks[0].estimated_tokens > 700
    assert any(warn.code.value == "OVERSIZED_TABLE_CHUNK" for warn in out.chunks[0].chunk_warnings)
