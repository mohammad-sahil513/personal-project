import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# Ensure the backend module is in python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.application.services.document_service import DocumentService
from backend.application.services.ingestion_orchestrator_adapter import RealIngestionOrchestratorAdapter
from backend.modules.ingestion.contracts.stage_1_contracts import Stage1Output, BlobArtifactReference, IngestionJobRecord, IngestionJobStatus, IngestionStageName, Stage1Metrics

async def test_phase1_ingestion_bridge():
    print("🚀 Starting Phase 1 Integration Test (Mocked Azure)...\n")

    # 1. Setup Document
    print("[1] Uploading mock document bytes to DocumentService...")
    doc_service = DocumentService()
    doc = doc_service.create_document(
        filename="test_architecture.pdf",
        content_type="application/pdf",
        size=1024,
        file_bytes=b"mock physical byte stream of pdf",
        status="READY"
    )
    print(f"   => Created Mock Document: {doc.document_id}")

    # 2. Setup Mock Pipeline Outputs
    mock_orchestrator = AsyncMock()
    
    mock_stage_1_out = Stage1Output(
        process_id="proc_123",
        document_id=doc.document_id,
        sha256_hash="a"*64,
        original_file=BlobArtifactReference(
            container_name="test",
            blob_path="sahil_storage/blob.pdf",
            content_type="application/pdf",
            size_bytes=1024
        ),
        is_duplicate=False,
        duplicate_of_document_id=None,
        job_record=IngestionJobRecord(
            process_id="proc_123",
            document_id=doc.document_id,
            file_name="test.pdf",
            content_type="application/pdf",
            sha256_hash="a"*64,
            source_blob=BlobArtifactReference(
                container_name="test",
                blob_path="sahil_storage/blob.pdf",
                content_type="application/pdf",
                size_bytes=1024
            ),
            status=IngestionJobStatus.COMPLETED,
            current_stage=IngestionStageName.UPLOAD_AND_DEDUP,
        ),
        metrics=Stage1Metrics(
            file_size_bytes=1024,
            upload_duration_ms=10.0,
            duplicate_lookup_duration_ms=5.0,
            total_duration_ms=15.0
        )
    )

    # Note: Using python dictionary Mock since the Adapter calls `.run(...)`
    # which returns a Pydantic IngestionPipelineResult
    class MockIngestionPipelineResult:
        def __init__(self):
            self.status = "COMPLETED"
            self.stage_1_output = mock_stage_1_out
            self.stage_2_output = None
            self.stage_3_output = None
    
    # Configure mock orchestrator's run output
    mock_orchestrator.run.return_value = MockIngestionPipelineResult()
    mock_orchestrator.execute.return_value = MockIngestionPipelineResult()

    adapter = RealIngestionOrchestratorAdapter()

    print("\n[2] Executing RealIngestionOrchestratorAdapter.run()...")
    
    # Patch live wiring so we don't instantiate real Azure clients
    mock_runtime = MagicMock()
    mock_runtime.run_ingestion = AsyncMock(return_value=MockIngestionPipelineResult())
    with patch(
        "backend.modules.ingestion.live_wiring.build_ingestion_runtime",
        return_value=mock_runtime,
    ):
        try:
            result = await adapter.run(
                workflow_run_id="wkflw_999",
                document_id=doc.document_id,
                ingestion_execution_id="ingest_888"
            )
            print(f"   => Successfully Normalized Result!")
            print(f"      Status:           {result['status']}")
            print(f"      Current Stage:    {result['current_stage']}")
            print(f"      Completed Stages: {result['completed_stages']} / {result['total_stages']}")
            print(f"      Warnings:         {len(result['warnings'])}")
            
            assert result["status"] == "COMPLETED", "Did not map COMPLETED correctly"
            assert result["completed_stages"] > 0, "Did not infer completed stages correctly"
            assert "09_vector_indexing" in result["current_stage"].lower()
            
            print("\n✅ Phase 1 Mock Test Passed! The Bridge handles payloads properly.\n")
        except Exception as e:
            print(f"\n❌ Phase 1 Mock Test Failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_phase1_ingestion_bridge())
