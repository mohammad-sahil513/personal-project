"""
Integration test: full ingestion pipeline (Stages 1 → 2 → 3 → 6 → 7 → 8).

Strategy:
- All Azure infrastructure clients (Blob Storage, Document Intelligence) are
  replaced with deterministic in-memory mocks.
- The IngestionRepository points at a pytest tmp_path directory.
- Every stage's output is validated against the next stage's input contract via
  the official from_stageN_output() factory helpers so that schema drift is
  caught immediately.
- No test-specific data is hard-coded into the services; we only control what
  the mock adapters return.
"""

from __future__ import annotations

import pytest

from backend.modules.ingestion.contracts.stage_1_contracts import (
    BlobArtifactReference,
    IngestionJobStatus,
    IngestionStageName,
    Stage1Input,
)
from backend.modules.ingestion.contracts.stage_2_contracts import Stage2Input
from backend.modules.ingestion.contracts.stage_3_contracts import Stage3Input
from backend.modules.ingestion.contracts.stage_6_contracts import Stage6Input
from backend.modules.ingestion.contracts.stage_7_contracts import Stage7Input
from backend.modules.ingestion.contracts.stage_8_contracts import Stage8Input
from backend.modules.ingestion.repositories.ingestion_repository import IngestionRepository
from backend.modules.ingestion.services.chunking_service import ChunkingService
from backend.modules.ingestion.services.parser_service import ParserService
from backend.modules.ingestion.services.pii_service import (
    PiiService,
    RegexPiiCandidateDetector,
    RuleBasedPiiClassifier,
)
from backend.modules.ingestion.services.segmentation_service import SegmentationService
from backend.modules.ingestion.services.upload_service import UploadService
from backend.modules.ingestion.services.validation_service import ValidationService

# ---------------------------------------------------------------------------
# Shared mock document: a realistic enough markdown document to exercise all
# pipeline stages without triggering degraded/failure paths.
# ---------------------------------------------------------------------------

_RICH_MARKDOWN = """\
# Project Overview

This document describes the functional requirements and architecture of the AI SDLC Engine.
Contact the project lead at projectlead@acme.com for enquiries.
Internal helpdesk is available at support@acme.com.

## Functional Requirements

The following requirements are defined for the initial delivery.

- REQ-001: The system shall ingest PDF and DOCX documents.
- REQ-002: The system shall detect and mask PII before indexing.
- NFR-001: End-to-end latency for a 50-page document must be under 120 seconds.

## Architecture

The ingestion pipeline is a staged, contract-driven modular monolith.

| Stage | Responsibility               |
|-------|------------------------------|
| 1     | Upload and deduplication     |
| 2     | Document parsing             |
| 3     | PII masking                  |
| 6     | Section segmentation         |
| 7     | Validation                   |
| 8     | Semantic chunking            |

## Security

Authentication and authorisation is handled via Azure AD with role-based access control.
Encryption at rest uses Azure Storage Service Encryption (SSE).
"""


# ---------------------------------------------------------------------------
# Inline mock adapters
# ---------------------------------------------------------------------------

class _InMemoryBlobClient:
    """Blob client that stores bytes in memory and returns valid references."""

    _CONTAINER = "sahil-test"
    _PREFIX = "sahil_storage/"

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def upload_bytes(
        self,
        *,
        container_name: str,
        blob_path: str,
        data: bytes,
        content_type: str,
        overwrite: bool = True,
    ) -> BlobArtifactReference:
        self._store[f"{container_name}/{blob_path}"] = data
        return BlobArtifactReference(
            container_name=container_name,
            blob_path=blob_path,
            content_type=content_type,
            size_bytes=len(data),
        )

    def get_bytes(self, blob_path: str) -> bytes | None:
        return self._store.get(f"{self._CONTAINER}/{blob_path}")


class _RichDocIntelClient:
    """Returns the shared rich markdown regardless of the source blob."""

    async def analyze_to_markdown(self, *, source_blob: BlobArtifactReference) -> str:
        return _RICH_MARKDOWN


# ---------------------------------------------------------------------------
# Pipeline fixture: wires all services together
# ---------------------------------------------------------------------------

@pytest.fixture()
def blob_client() -> _InMemoryBlobClient:
    return _InMemoryBlobClient()


@pytest.fixture()
def repository(tmp_path):
    return IngestionRepository(base_dir=tmp_path / "ingestion_repo")


@pytest.fixture()
def upload_service(blob_client, repository) -> UploadService:
    return UploadService(
        blob_client=blob_client,
        repository=repository,
        blob_container_name=_InMemoryBlobClient._CONTAINER,
        blob_root_prefix=_InMemoryBlobClient._PREFIX,
    )


@pytest.fixture()
def parser_service(blob_client) -> ParserService:
    return ParserService(
        document_intelligence_client=_RichDocIntelClient(),
        blob_client=blob_client,
        blob_container_name=_InMemoryBlobClient._CONTAINER,
        blob_root_prefix=_InMemoryBlobClient._PREFIX,
    )


@pytest.fixture()
def pii_service(blob_client) -> PiiService:
    return PiiService(
        candidate_detector=RegexPiiCandidateDetector(),
        classifier=RuleBasedPiiClassifier(),
        blob_client=blob_client,
        blob_container_name=_InMemoryBlobClient._CONTAINER,
        blob_root_prefix=_InMemoryBlobClient._PREFIX,
    )


@pytest.fixture()
def segmentation_service() -> SegmentationService:
    return SegmentationService()


@pytest.fixture()
def validation_service() -> ValidationService:
    return ValidationService()


@pytest.fixture()
def chunking_service() -> ChunkingService:
    return ChunkingService()


# ---------------------------------------------------------------------------
# Integration test: full pipeline Stage 1 → 8
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_pipeline_stage1_to_stage8(
    upload_service,
    parser_service,
    pii_service,
    segmentation_service,
    validation_service,
    chunking_service,
    repository,
):
    """
    Full ingestion pipeline integration: Stage 1 → 2 → 3 → 6 → 7 → 8.

    Verifies:
    1. Stage 1 creates a job record with IN_PROGRESS status.
    2. Stage 2 parses the mock document into valid enriched markdown with
       at least one heading detected.
    3. Stage 3 masks exactly one personal PII email (projectlead@acme.com)
       and preserves the system email (support@acme.com via allowlist).
    4. Stage 6 segments into ≥ 3 sections (overview + requirements + arch/security).
    5. Stage 7 validation reports no global failures.
    6. Stage 8 produces ≥ 1 chunk per section and every chunk has a populated
       content field with ≥ 1 estimated token.
    """

    # ── Stage 1: Upload & Deduplicate ──────────────────────────────────────
    stage1_input = Stage1Input(
        file_name="project_overview.pdf",
        content_type="application/pdf",
        file_bytes=b"%PDF fake payload",
        initiated_by="integration_test",
        correlation_id="IT-001",
        source_metadata={"project": "AI-SDLC"},
    )
    stage1_out = await upload_service.upload_and_deduplicate(stage1_input)

    assert stage1_out.is_duplicate is False
    assert stage1_out.sha256_hash is not None and len(stage1_out.sha256_hash) == 64
    assert stage1_out.job_record.status == IngestionJobStatus.IN_PROGRESS

    # Verify the job was persisted
    persisted_job = await repository.get_job_by_document_id(stage1_out.document_id)
    assert persisted_job is not None
    assert persisted_job.current_stage == IngestionStageName.UPLOAD_AND_DEDUP

    # ── Stage 2: Parse Document ────────────────────────────────────────────
    stage2_input = Stage2Input.from_stage_1_output(stage1_out)
    stage2_out = await parser_service.parse_document(stage2_input)

    assert "Project Overview" in stage2_out.raw_markdown
    assert stage2_out.parse_quality_report.heading_count >= 3
    assert stage2_out.parse_quality_report.estimated_tokens > 50
    assert stage2_out.parse_quality_report.table_count >= 1

    # ── Stage 3: PII Masking ───────────────────────────────────────────────
    stage3_input = Stage3Input.from_stage_2_output(
        stage2_out,
        pii_enabled=True,
        system_email_allowlist=["support@acme.com"],
    )
    stage3_out = await pii_service.process_pii(stage3_input)

    # projectlead@acme.com  → masked
    # support@acme.com      → kept (allowlisted)
    assert stage3_out.metrics.total_candidates_detected >= 2
    assert stage3_out.metrics.total_candidates_masked >= 1
    assert stage3_out.metrics.total_candidates_kept >= 1
    assert "projectlead@acme.com" not in stage3_out.masked_markdown
    assert "support@acme.com" in stage3_out.masked_markdown
    assert "[PII_EMAIL_001]" in stage3_out.masked_markdown

    # ── Stage 6: Section Segmentation ─────────────────────────────────────
    # Build Stage 6 input directly from Stage 3 output fields (no skipped stages)
    stage6_input = Stage6Input(
        process_id=stage3_out.process_id,
        document_id=stage3_out.document_id,
        source_blob=stage3_out.source_blob,
        enriched_markdown=stage3_out.masked_markdown,
        enriched_markdown_artifact=stage3_out.masked_markdown_artifact,
        asset_registry=stage3_out.asset_registry,
        hyperlink_registry=stage3_out.hyperlink_registry,
        table_registry=stage3_out.table_registry,
        parse_quality_report=stage3_out.parse_quality_report,
        prior_warnings=stage3_out.warnings,
    )
    stage6_out = segmentation_service.segment_document(stage6_input)

    # The rich markdown has 4 H1/H2 headings: Overview, Requirements, Architecture, Security
    assert len(stage6_out.sections) >= 3
    section_headings = [s.heading for s in stage6_out.sections]
    assert any("Overview" in h for h in section_headings)
    assert any("Requirement" in h for h in section_headings)

    # ── Stage 7: Validation ────────────────────────────────────────────────
    stage7_input = Stage7Input.from_stage_6_output(
        stage6_out,
        parse_quality_report=stage3_out.parse_quality_report,
        asset_registry=stage3_out.asset_registry,
        pii_enabled=True,
        mapped_pii_values=["projectlead@acme.com"],       # original values already masked
        allowlisted_system_emails=["support@acme.com"],
    )
    stage7_out = validation_service.validate(stage7_input)

    assert stage7_out.summary.has_global_failure is False, (
        f"Stage 7 reported unexpected global failure: {[i.code for i in stage7_out.issues]}"
    )
    assert stage7_out.summary.can_proceed_to_chunking is True

    # ── Stage 8: Semantic Chunking ─────────────────────────────────────────
    stage8_input = Stage8Input.from_stage_7_output(stage7_out)
    stage8_out = chunking_service.chunk_document(stage8_input)

    assert stage8_out.metrics.total_sections_processed == len(stage6_out.sections)
    assert stage8_out.metrics.total_chunks_created >= len(stage6_out.sections)
    assert all(chk.content for chk in stage8_out.chunks)
    assert all(chk.estimated_tokens >= 1 for chk in stage8_out.chunks)
    assert all(chk.document_id == stage1_out.document_id for chk in stage8_out.chunks)

    # Requirements section should have requirement IDs extracted
    req_chunks = [c for c in stage8_out.chunks if "REQUIREMENT" in c.section_type]
    req_ids = [rid for c in req_chunks for rid in c.requirement_ids]
    assert len(req_ids) > 0, "Expected requirement IDs to be extracted from the requirements section."


# ---------------------------------------------------------------------------
# Integration test: duplicate detection across two independent uploads
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_duplicate_detection(upload_service, repository):
    """Uploading the same bytes twice must result in a DUPLICATE job on the second call."""

    payload = b"%PDF identical content"

    first_input = Stage1Input(
        file_name="doc_a.pdf",
        content_type="application/pdf",
        file_bytes=payload,
        initiated_by="user_a",
        correlation_id="IT-DUP-001",
        source_metadata={},
    )
    second_input = Stage1Input(
        file_name="doc_b.pdf",
        content_type="application/pdf",
        file_bytes=payload,
        initiated_by="user_b",
        correlation_id="IT-DUP-002",
        source_metadata={},
    )

    out1 = await upload_service.upload_and_deduplicate(first_input)
    out2 = await upload_service.upload_and_deduplicate(second_input)

    assert out1.is_duplicate is False
    assert out2.is_duplicate is True
    assert out2.duplicate_of_document_id == out1.document_id
    assert out2.job_record.status == IngestionJobStatus.DUPLICATE
    assert len(out2.warnings) == 1
    assert out2.warnings[0].code == "DUPLICATE_DOCUMENT_DETECTED"

    # Registry should still resolve both document IDs to the canonical original
    canonical = await repository.get_job_by_sha256_hash(out1.sha256_hash)
    assert canonical.document_id == out1.document_id


# ---------------------------------------------------------------------------
# Integration test: Stage 7 blocks chunking when validation fails
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pipeline_validation_blocks_chunking_on_error(
    upload_service,
    parser_service,
    segmentation_service,
    validation_service,
    chunking_service,
):
    """
    When Stage 7 detects a global error, Stage 8 must raise ChunkingError and refuse to run.
    """
    from backend.modules.ingestion.contracts.stage_2_contracts import (
        AssetRegistry,
        ParseQualityReport,
        ParseQualityTier,
    )
    from backend.modules.ingestion.contracts.stage_6_contracts import (
        SegmentedSection,
        SectionType,
        StructuralSignals,
    )
    from backend.modules.ingestion.contracts.stage_7_contracts import (
        Stage7Input,
        ValidationSummary,
    )
    from backend.modules.ingestion.contracts.stage_8_contracts import Stage8Input
    from backend.modules.ingestion.exceptions import ChunkingError

    source_blob = BlobArtifactReference(
        container_name="test",
        blob_path="sahil_storage/source.pdf",
        content_type="application/pdf",
        size_bytes=100,
    )
    artifact = BlobArtifactReference(
        container_name="test",
        blob_path="sahil_storage/md/enriched.md",
        content_type="text/markdown",
        size_bytes=10,
    )
    section = SegmentedSection(
        section_id="sec_001_overview",
        heading="Overview",
        heading_level=1,
        section_index=1,
        section_type=SectionType.OVERVIEW,
        raw_content="Some content.",
        preview_text="Some content.",
        structural_signals=StructuralSignals(
            has_table=False,
            has_list=False,
            has_requirement_pattern=False,
            has_asset_reference=False,
            has_h3_subheading=False,
            estimated_tokens=5,
        ),
        warnings=[],
    )

    # Craft a Stage 7 input with a degraded parse report (0 tokens, 0 headings → ERROR)
    degraded_quality = ParseQualityReport(
        heading_count=0,
        image_count=0,
        table_count=0,
        hyperlink_count=0,
        estimated_tokens=0,
        quality_tier=ParseQualityTier.DEGRADED,
        embedded_object_detected=False,
        warnings=[],
    )

    stage7_input = Stage7Input(
        process_id="proc_blocked",
        document_id="doc_blocked",
        source_blob=source_blob,
        sections=[section],
        parse_quality_report=degraded_quality,
        asset_registry=AssetRegistry(assets=[]),
        enriched_markdown_artifact=artifact,
        pii_enabled=False,
        allowlisted_system_emails=[],
        mapped_pii_values=[],
        prior_warnings=[],
    )
    stage7_out = validation_service.validate(stage7_input)

    # Stage 7 must have detected a global failure due to empty markdown
    assert stage7_out.summary.has_global_failure is True
    assert stage7_out.summary.can_proceed_to_chunking is False

    # Stage 8 must refuse to run when validation says it cannot proceed
    stage8_input = Stage8Input.from_stage_7_output(stage7_out)
    with pytest.raises(ChunkingError):
        chunking_service.chunk_document(stage8_input)
