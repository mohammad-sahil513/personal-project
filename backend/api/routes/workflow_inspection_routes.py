"""
Workflow inspection routes.
"""

from fastapi import APIRouter, Depends, Query

from backend.api.dependencies import get_api_logger
from backend.application.services.workflow_inspection_service import (
    WorkflowInspectionService,
)
from backend.core.response import success_response

router = APIRouter(prefix="/workflow-runs", tags=["workflow-inspection"])


@router.get("/{workflow_run_id}/errors")
async def get_workflow_errors(
    workflow_run_id: str,
    logger=Depends(get_api_logger),
):
    service = WorkflowInspectionService()
    data = service.get_errors(workflow_run_id)

    logger.info("Workflow errors fetched", extra={"workflow_run_id": workflow_run_id})
    return success_response(message="Workflow errors fetched", data=data)


@router.get("/{workflow_run_id}/artifacts")
async def get_workflow_artifacts(
    workflow_run_id: str,
    logger=Depends(get_api_logger),
):
    service = WorkflowInspectionService()
    data = service.get_artifacts(workflow_run_id)

    logger.info("Workflow artifacts fetched", extra={"workflow_run_id": workflow_run_id})
    return success_response(message="Workflow artifacts fetched", data=data)


@router.get("/{workflow_run_id}/events/snapshot")
async def get_workflow_events_snapshot(
    workflow_run_id: str,
    limit: int = Query(20, ge=1, le=100),
    logger=Depends(get_api_logger),
):
    service = WorkflowInspectionService()
    data = service.get_recent_events(workflow_run_id, limit=limit)

    logger.info("Workflow events snapshot fetched", extra={"workflow_run_id": workflow_run_id})
    return success_response(message="Workflow events snapshot fetched", data=data)


@router.get("/{workflow_run_id}/diagnostics")
async def get_workflow_diagnostics(
    workflow_run_id: str,
    logger=Depends(get_api_logger),
):
    service = WorkflowInspectionService()
    data = service.get_diagnostics(workflow_run_id)

    logger.info("Workflow diagnostics fetched", extra={"workflow_run_id": workflow_run_id})
    return success_response(message="Workflow diagnostics fetched", data=data)