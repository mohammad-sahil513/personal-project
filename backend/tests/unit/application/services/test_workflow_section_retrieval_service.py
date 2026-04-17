from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.application.services.workflow_section_retrieval_service import (
    WorkflowSectionRetrievalService,
)


@pytest.mark.asyncio
async def test_run_retrieval_publishes_started_and_completed_events():
    retrieval_service = AsyncMock()
    retrieval_result = MagicMock()
    retrieval_result.section_id = "sec_1"
    retrieval_result.to_dict.return_value = {
        "section_id": "sec_1",
        "overall_confidence": 0.9,
        "evidence_bundle": {"items": [{"id": "ev1"}]},
        "diagnostics": {"fallback_used": False, "cost_summary": {"total_amount": 0.001}},
        "warnings": [],
    }
    retrieval_service.retrieve_for_section.return_value = retrieval_result

    workflow_event_service = AsyncMock()

    service = WorkflowSectionRetrievalService(
        section_retrieval_service=retrieval_service,
        workflow_event_service=workflow_event_service,
    )

    result = await service.run_retrieval_for_workflow(
        section_plan={"sections": [{"section_id": "sec_1", "title": "S1"}]},
        workflow_run_id="wf_1",
        document_id="doc_1",
        template_id="tpl_1",
    )

    assert "sec_1" in result
    assert workflow_event_service.publish.await_count == 2
    first_payload = workflow_event_service.publish.await_args_list[0].kwargs["payload"]
    second_payload = workflow_event_service.publish.await_args_list[1].kwargs["payload"]
    assert first_payload["status"] == "STARTED"
    assert second_payload["status"] == "COMPLETED"
    assert second_payload["evidence_count"] == 1


@pytest.mark.asyncio
async def test_run_retrieval_publishes_failed_event():
    retrieval_service = AsyncMock()
    retrieval_service.retrieve_for_section.side_effect = RuntimeError("retrieval boom")
    workflow_event_service = AsyncMock()

    service = WorkflowSectionRetrievalService(
        section_retrieval_service=retrieval_service,
        workflow_event_service=workflow_event_service,
    )

    with pytest.raises(RuntimeError, match="retrieval boom"):
        await service.run_retrieval_for_workflow(
            section_plan={"sections": [{"section_id": "sec_1", "title": "S1"}]},
            workflow_run_id="wf_1",
            document_id="doc_1",
            template_id="tpl_1",
        )

    assert workflow_event_service.publish.await_count == 2
    failed_payload = workflow_event_service.publish.await_args_list[1].kwargs["payload"]
    assert failed_payload["status"] == "FAILED"
    assert "retrieval boom" in failed_payload["error"]
