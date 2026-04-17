import pytest
from pydantic import ValidationError

from backend.modules.ingestion.contracts.stage_1_contracts import (
    Stage1Input,
    BlobArtifactReference,
    IngestionJobRecord,
    IngestionStageName,
    StageExecutionStatus,
    IngestionJobStatus
)
from backend.modules.ingestion.contracts.stage_2_contracts import Stage2Input, AssetRegistry, TableRegistry, ParseQualityReport, ParseQualityTier, HyperlinkRegistry
from backend.modules.ingestion.contracts.stage_3_contracts import Stage3Input, PiiCandidate, PiiDecisionAction, PiiEntityType, ContextualPiiDecision


def test_stage1_contracts():
    valid_input = Stage1Input(
        file_name="test.pdf",
        content_type="application/pdf",
        file_bytes=b"dummy",
        initiated_by="user_abc",
        correlation_id="corr_abc",
        source_metadata={}
    )
    assert valid_input.file_name == "test.pdf"

    # Test forbid extra
    with pytest.raises(ValidationError):
        Stage1Input(
            file_name="test.pdf",
            content_type="application/pdf",
            file_bytes=b"dummy",
            initiated_by="user",
            correlation_id="corr",
            source_metadata={},
            extra_field="NO"
        )


def test_stage2_contracts():
    source_blob = BlobArtifactReference(
        container_name="test",
        blob_path="sahil_storage/src",
        content_type="text/plain",
        size_bytes=10
    )
    valid_input = Stage2Input(
        process_id="proc_123",
        document_id="doc_123",
        sha256_hash="a"*64,
        source_blob=source_blob,
        prior_warnings=[],
        file_name="test.pdf",
        content_type="application/pdf"
    )
    assert valid_input.document_id == "doc_123"


def test_stage3_contracts():
    candidate = PiiCandidate(
        candidate_id="c_001",
        entity_type=PiiEntityType.EMAIL_ADDRESS,
        matched_text="test@example.com",
        start_char=10,
        end_char=26
    )
    assert candidate.entity_type == PiiEntityType.EMAIL_ADDRESS

    decision = ContextualPiiDecision(
        candidate_id="c_001",
        entity_type=PiiEntityType.EMAIL_ADDRESS,
        action=PiiDecisionAction.KEEP,
        reason="It's safe"
    )
    assert decision.action == PiiDecisionAction.KEEP
