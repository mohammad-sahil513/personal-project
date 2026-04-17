"""
Workflow SSE event routes.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from backend.api.dependencies import get_api_logger, get_workflow_event_broker
from backend.application.services.workflow_event_service import WorkflowEventService

router = APIRouter(prefix="/workflow-runs", tags=["workflow-events"])


@router.get("/{workflow_run_id}/events")
async def stream_workflow_events(
    workflow_run_id: str,
    event_service: WorkflowEventService = Depends(get_workflow_event_broker),
    logger=Depends(get_api_logger),
):
    logger.info(
        "Workflow SSE stream opened",
        extra={"workflow_run_id": workflow_run_id},
    )

    return StreamingResponse(
        event_service.stream(workflow_run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )