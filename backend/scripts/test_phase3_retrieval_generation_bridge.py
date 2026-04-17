import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Ensure the backend module is in python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.application.services.retrieval_runtime_bridge import RetrievalRuntimeBridge
from backend.application.services.generation_runtime_bridge import GenerationRuntimeBridge

async def test_phase3_bridges():
    print("🚀 Starting Phase 3 Retrieval & Generation Bridge Mock Test...\n")

    # --- 1. Retrieval Bridge ---
    print("[1] Executing Retrieval Bridge Mock...")
    mock_retrieval_runtime = AsyncMock()
    mock_retrieval_runtime.retrieve.return_value = {
        "status": "COMPLETED",
        "overall_confidence": 0.95,
        "evidence_bundle": {"docs_found": 3, "chunks": ["chunk1", "chunk2"]},
        "diagnostics": {"time_ms": 120},
        "warnings": [],
        "errors": []
    }

    retrieval_bridge = RetrievalRuntimeBridge()
    
    with patch("backend.application.services.retrieval_runtime_bridge.RetrievalRuntimeBridge._build_default_runtime_callable", return_value=mock_retrieval_runtime.retrieve):
        retrieval_res = await retrieval_bridge.run_retrieval(
            section_id="sec_001",
            title="Executive Summary",
            retrieval_profile="DEEP_DIVE",
            generation_strategy="SUMMARIZE"
        )
        
        assert retrieval_res["status"] == "COMPLETED"
        assert retrieval_res["overall_confidence"] == 0.95
        assert retrieval_res["evidence_bundle"]["docs_found"] == 3
        print("   => Retrieval Normalization Passed!")

    # --- 2. Generation Bridge ---
    print("\n[2] Executing Generation Bridge Mock...")
    mock_generation_runtime = AsyncMock()
    
    class MockGenResult:
        def __init__(self):
            self.status = "COMPLETED"
            self.output_type = "MARKDOWN"
            self.content = "## Executive Summary\nThis is a mocked generated text."
            self.artifacts = []
            self.diagnostics = {"tokens": 250}
            self.warnings = []
            self.errors = []
            
    mock_generation_runtime.execute_section.return_value = MockGenResult()

    generation_bridge = GenerationRuntimeBridge()
    
    with patch("backend.application.services.generation_runtime_bridge.GenerationRuntimeBridge._build_default_runtime_callable", return_value=mock_generation_runtime.execute_section):
        generation_res = await generation_bridge.run_generation(
            section_id="sec_001",
            title="Executive Summary",
            generation_strategy="SUMMARIZE",
            retrieval_result=retrieval_res
        )
        
        assert generation_res["status"] == "COMPLETED"
        assert generation_res["output_type"] == "MARKDOWN"
        assert "mocked generated text" in generation_res["content"]
        print("   => Generation Normalization Passed!")

    print("\n✅ Phase 3 Mock Test Passed! Generators validate correctly.\n")


if __name__ == "__main__":
    asyncio.run(test_phase3_bridges())
