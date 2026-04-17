import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

# Ensure the backend module is in python path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.application.services.template_app_service import TemplateAppService
from backend.application.services.section_planning_service import SectionPlanningService
from backend.core.exceptions import ValidationError

async def test_phase2_template_bridge():
    print("🚀 Starting Phase 2 Template Bridge Integration Test...\n")

    # 1. Simulate Template Upload (Strict Separation from Workflows)
    print("[1] Uploading mock Template DOCX to TemplateAppService...")
    template_service = TemplateAppService()
    
    mock_docx_bytes = b"PK\x03\x04mockdocxcontent"
    template = template_service.create_template(
        filename="master_proposal_template.docx",
        template_type="PROPOSAL",
        version="1.0.0",
        file_bytes=mock_docx_bytes
    )
    print(f"   => Created Mock Template: {template.template_id}")

    # 2. Simulate Template Resolution (Mocking the AI/Agent compiler)
    print("\n[2] Executing SectionPlanningService.build_plan_dict()...")

    # We patch TemplateResolveBridge instead of running actual AI text-to-JSON
    from backend.api.schemas.template import ResolvedTemplateSection
    
    mock_resolved_sections = [
        {"section_id": "sec_002", "title": "Sub Section 1", "execution_order": 2, "generation_strategy": "CONTEXTUAL", "dependencies": ["sec_001"]},
        {"section_id": "sec_001", "title": "Executive Summary", "execution_order": 1, "generation_strategy": "SUMMARIZE", "dependencies": []},
        {"section_id": "sec_003", "title": "Conclusion", "execution_order": 3, "generation_strategy": "EXTRACT", "dependencies": ["sec_001", "sec_002"]}
    ]
    
    mock_bridge_run = AsyncMock()
    mock_bridge_run.return_value = {
        "status": "COMPLETED",
        "resolved_sections": mock_resolved_sections
    }

    print("\n[2] Executing SectionPlanningService.build_plan_dict()...")

    with patch("backend.application.services.template_resolve_bridge.TemplateResolveBridge.run_resolve", new=mock_bridge_run):
        planner = SectionPlanningService()

        try:
            plan = await planner.build_plan_dict(template.template_id)
            
            print("   => Successfully Built Section Plan!")
            print(f"      Total Sections: {plan['total_sections']}")
            
            # Verify dependency sorting (sec_001 must come before sec_002)
            exec_orders = [s["execution_order"] for s in plan["sections"]]
            print(f"      Execution Orders: {exec_orders}")
            
            # Validate that topological sort didn't break
            titles = [s["title"] for s in plan["sections"]]
            print(f"      Section Order: {titles}")
            
            assert titles[0] == "Executive Summary"
            assert titles[1] == "Sub Section 1"
            assert titles[2] == "Conclusion"

            print("\n✅ Phase 2 Mock Test Passed! Templates successfully map to Execution Plans.\n")
        except Exception as e:
            print(f"\n❌ Phase 2 Mock Test Failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_phase2_template_bridge())
