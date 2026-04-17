"""
Workflow route handlers.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends

from backend.api.dependencies import get_api_logger
from backend.api.schemas.workflow import WorkflowCreateRequest
from backend.application.services.ingestion_integration_service import (
    IngestionIntegrationService,
)
from backend.application.services.ingestion_status_service import IngestionStatusService
from backend.application.services.workflow_executor_service import WorkflowExecutorService
from backend.application.services.workflow_service import WorkflowService
from backend.core.config import get_settings
from backend.core.response import success_response

router = APIRouter(prefix="/workflow-runs", tags=["workflow"])


@router.post("")
async def create_workflow(
    payload: WorkflowCreateRequest,
    background_tasks: BackgroundTasks,
    logger=Depends(get_api_logger),
) -> dict:
    workflow_service = WorkflowService()
    executor_service = WorkflowExecutorService(workflow_service=workflow_service)

    created = workflow_service.create_workflow(
        document_id=payload.document_id,
        template_id=payload.template_id,
    )

    dispatch_mode = None
    if payload.start_immediately:
        dispatch_result = executor_service.dispatch_workflow_execution(
            created.workflow_run_id,
            background_tasks=background_tasks,
        )
        dispatch_mode = dispatch_result["dispatch_mode"]

    latest = workflow_service.get_workflow(created.workflow_run_id)
    data = latest.to_dict()
    data["dispatch_mode"] = dispatch_mode

    logger.info(
        "Workflow created via API",
        extra={
            "workflow_run_id": created.workflow_run_id,
            "dispatch_mode": dispatch_mode,
        },
    )

    return success_response(
        message="Workflow created successfully",
        data=data,
    )


@router.get("")
async def list_workflows(
    logger=Depends(get_api_logger),
) -> dict:
    workflow_service = WorkflowService()
    items = [item.to_dict() for item in workflow_service.list_workflows()]

    logger.info("Workflow list fetched", extra={"count": len(items)})

    return success_response(
        message="Workflow runs fetched successfully",
        data={
            "items": items,
            "total": len(items),
        },
    )


@router.get("/{workflow_run_id}")
async def get_workflow(
    workflow_run_id: str,
    logger=Depends(get_api_logger),
) -> dict:
    workflow_service = WorkflowService()
    item = workflow_service.get_workflow(workflow_run_id)

    logger.info(
        "Workflow fetched",
        extra={"workflow_run_id": workflow_run_id},
    )

    return success_response(
        message="Workflow fetched successfully",
        data=item.to_dict(),
    )


@router.get("/{workflow_run_id}/status")
async def get_workflow_status(
    workflow_run_id: str,
    logger=Depends(get_api_logger),
) -> dict:
    workflow_service = WorkflowService()
    ingestion_service = IngestionIntegrationService()
    ingestion_status_service = IngestionStatusService()

    item = workflow_service.get_workflow(workflow_run_id)

    current_step_label = None
    ingestion_block = None

    ingestion_exec_id = (item.execution_refs or {}).get("INGESTION")
    if ingestion_exec_id:
        ingestion_exec = ingestion_service.get_ingestion_execution(ingestion_exec_id)
        ingestion_block = ingestion_status_service.build_status_block(ingestion_exec)

        if item.current_phase == "INGESTION" or ingestion_exec.status in {"FAILED", "COMPLETED"}:
            current_step_label = ingestion_status_service.build_step_label(ingestion_exec)

    if current_step_label is None:
        if item.current_phase == "INPUT_PREPARATION":
            current_step_label = "Preparing workflow inputs"
        elif item.current_phase == "TEMPLATE_PREPARATION":
            current_step_label = "Workflow is in template preparation phase"
        elif item.current_phase == "SECTION_PLANNING":
            current_step_label = "Workflow is in section planning phase"
        elif item.current_phase == "RETRIEVAL":
            current_step_label = "Workflow is in retrieval phase"
        elif item.current_phase == "GENERATION":
            current_step_label = "Workflow is in generation phase"
        elif item.current_phase == "ASSEMBLY_VALIDATION":
            current_step_label = "Workflow is assembling and validating output"
        elif item.current_phase == "RENDER_EXPORT":
            current_step_label = "Workflow is rendering/exporting the final output"

    logger.info(
        "Workflow status fetched",
        extra={
            "workflow_run_id": workflow_run_id,
            "current_phase": item.current_phase,
            "overall_progress_percent": item.overall_progress_percent,
            "has_ingestion_block": ingestion_block is not None,
            "has_section_progress": item.section_progress is not None,
        },
    )

    data = item.to_dict()
    data["current_step_label"] = current_step_label
    data["ingestion"] = ingestion_block

    return success_response(
        message="Workflow status fetched successfully",
        data=data,
    )


@router.get("/{workflow_run_id}/sections")
async def get_workflow_sections(
    workflow_run_id: str,
    logger=Depends(get_api_logger),
) -> dict:
    workflow_service = WorkflowService()
    workflow = workflow_service.get_workflow(workflow_run_id)

    if not workflow.section_plan:
        logger.info(
            "Workflow section plan requested but not available",
            extra={"workflow_run_id": workflow_run_id},
        )
        return success_response(
            message="No section plan available for this workflow",
            data={
                "workflow_run_id": workflow_run_id,
                "template_id": workflow.template_id,
                "total_sections": 0,
                "sections": [],
            },
        )

    logger.info(
        "Workflow section plan fetched",
        extra={
            "workflow_run_id": workflow_run_id,
            "total_sections": workflow.section_plan.get("total_sections"),
        },
    )

    return success_response(
        message="Workflow section plan fetched successfully",
        data={
            "workflow_run_id": workflow_run_id,
            "template_id": workflow.section_plan.get("template_id"),
            "total_sections": workflow.section_plan.get("total_sections"),
            "sections": workflow.section_plan.get("sections", []),
        },
    )


def _read_latest_json_log_event(log_path: Path) -> dict | None:
    if not log_path.exists() or not log_path.is_file():
        return None
    try:
        lines = log_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return None
    for line in reversed(lines):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return None


def _build_generation_cost_summary(workflow_dict: dict) -> dict:
    section_generation_results = workflow_dict.get("section_generation_results") or {}
    total_amount = 0.0
    counted_sections = 0
    for section_result in section_generation_results.values():
        if not isinstance(section_result, dict):
            continue
        diagnostics = section_result.get("diagnostics") or {}
        if not isinstance(diagnostics, dict):
            continue
        cost_metadata = diagnostics.get("cost_metadata") or {}
        if not isinstance(cost_metadata, dict):
            continue
        estimate = cost_metadata.get("estimate") or {}
        if not isinstance(estimate, dict):
            continue
        amount = estimate.get("amount")
        if isinstance(amount, (int, float)):
            total_amount += float(amount)
            counted_sections += 1
    return {
        "estimated_generation_cost_total": round(total_amount, 10),
        "sections_with_cost": counted_sections,
    }


def _build_retrieval_cost_summary(workflow_dict: dict) -> dict:
    section_retrieval_results = workflow_dict.get("section_retrieval_results") or {}
    total_amount = 0.0
    counted_sections = 0
    for section_result in section_retrieval_results.values():
        if not isinstance(section_result, dict):
            continue
        diagnostics = section_result.get("diagnostics") or {}
        if not isinstance(diagnostics, dict):
            continue
        cost_summary = diagnostics.get("cost_summary") or {}
        if not isinstance(cost_summary, dict):
            continue
        amount = cost_summary.get("total_amount")
        if isinstance(amount, (int, float)):
            total_amount += float(amount)
            counted_sections += 1
    return {
        "estimated_retrieval_cost_total": round(total_amount, 10),
        "sections_with_cost": counted_sections,
    }


def _build_ingestion_cost_summary(latest_ingestion_event: dict | None) -> dict:
    if not isinstance(latest_ingestion_event, dict):
        return {"estimated_ingestion_cost_total": 0.0}
    safe_metadata = latest_ingestion_event.get("safe_metadata") or {}
    if not isinstance(safe_metadata, dict):
        return {"estimated_ingestion_cost_total": 0.0}
    cost = safe_metadata.get("cost") or {}
    if not isinstance(cost, dict):
        return {"estimated_ingestion_cost_total": 0.0}
    amount = cost.get("amount", 0.0)
    if not isinstance(amount, (int, float)):
        amount = 0.0
    return {
        "estimated_ingestion_cost_total": round(float(amount), 10),
        "line_items": cost.get("line_items", []),
    }


def _build_phase_status_breakdown(workflow_dict: dict) -> dict:
    result: dict[str, dict] = {}
    for phase in (workflow_dict.get("phases") or []):
        if not isinstance(phase, dict):
            continue
        phase_name = str(phase.get("phase", "")).lower()
        result[phase_name] = {
            "status": phase.get("status"),
            "progress_percent": phase.get("progress_percent"),
            "started_at": phase.get("started_at"),
            "completed_at": phase.get("completed_at"),
        }
    return result


def _build_final_observability_summary(workflow_dict: dict, latest_ingestion_event: dict | None) -> dict:
    generation_cost = _build_generation_cost_summary(workflow_dict)
    retrieval_cost = _build_retrieval_cost_summary(workflow_dict)
    ingestion_cost = _build_ingestion_cost_summary(latest_ingestion_event)
    stage_statuses = _build_phase_status_breakdown(workflow_dict)
    stage_statuses.setdefault("assembly", {"status": "COMPLETED" if workflow_dict.get("assembled_document") else "PENDING"})
    stage_statuses.setdefault("export", {"status": "COMPLETED" if workflow_dict.get("output_id") else "PENDING"})

    generation_total = float(generation_cost.get("estimated_generation_cost_total", 0.0))
    retrieval_total = float(retrieval_cost.get("estimated_retrieval_cost_total", 0.0))
    ingestion_total = float(ingestion_cost.get("estimated_ingestion_cost_total", 0.0))
    document_total = ingestion_total + retrieval_total + generation_total

    return {
        "workflow_run_id": workflow_dict.get("workflow_run_id"),
        "document_id": workflow_dict.get("document_id"),
        "template_id": workflow_dict.get("template_id"),
        "status": workflow_dict.get("status"),
        "current_phase": workflow_dict.get("current_phase"),
        "stage_statuses": stage_statuses,
        "cost_totals": {
            "ingestion": round(ingestion_total, 10),
            "retrieval": round(retrieval_total, 10),
            "generation": round(generation_total, 10),
            "assembly": 0.0,
            "export": 0.0,
            "document_total": round(document_total, 10),
        },
        "per_section_totals": {
            "retrieval": {
                section_id: (result.get("diagnostics", {}).get("cost_summary", {}).get("total_amount", 0.0))
                for section_id, result in (workflow_dict.get("section_retrieval_results") or {}).items()
                if isinstance(result, dict)
            },
            "generation": {
                section_id: (result.get("diagnostics", {}).get("cost_metadata", {}).get("estimate", {}).get("amount", 0.0))
                for section_id, result in (workflow_dict.get("section_generation_results") or {}).items()
                if isinstance(result, dict)
            },
        },
    }


@router.get("/{workflow_run_id}/observability")
async def get_workflow_observability(
    workflow_run_id: str,
    logger=Depends(get_api_logger),
) -> dict:
    settings = get_settings()
    workflow_service = WorkflowService()
    workflow = workflow_service.get_workflow(workflow_run_id)
    workflow_dict = workflow.to_dict()

    run_root = settings.logs_path / "ingestion_runs" / workflow_run_id
    logs_dir = run_root / "logs"
    artifacts_dir = run_root / "artifacts"
    official_log_path = logs_dir / "official.log"
    demo_log_path = logs_dir / "demo.log"

    latest_ingestion_event = _read_latest_json_log_event(official_log_path)
    generation_cost_summary = _build_generation_cost_summary(workflow_dict)
    retrieval_cost_summary = _build_retrieval_cost_summary(workflow_dict)
    ingestion_cost_summary = _build_ingestion_cost_summary(latest_ingestion_event)
    final_summary = _build_final_observability_summary(workflow_dict, latest_ingestion_event)

    logger.info(
        "Workflow observability fetched",
        extra={
            "workflow_run_id": workflow_run_id,
            "has_official_log": official_log_path.exists(),
            "has_demo_log": demo_log_path.exists(),
            "has_artifacts_dir": artifacts_dir.exists(),
        },
    )

    return success_response(
        message="Workflow observability fetched successfully",
        data={
            "workflow_run_id": workflow_run_id,
            "paths": {
                "run_root": str(run_root),
                "logs_dir": str(logs_dir),
                "artifacts_dir": str(artifacts_dir),
                "official_log": str(official_log_path),
                "demo_log": str(demo_log_path),
            },
            "availability": {
                "run_root_exists": run_root.exists(),
                "logs_dir_exists": logs_dir.exists(),
                "artifacts_dir_exists": artifacts_dir.exists(),
                "official_log_exists": official_log_path.exists(),
                "demo_log_exists": demo_log_path.exists(),
            },
            "latest_summary": {
                "workflow_status": workflow_dict.get("status"),
                "current_phase": workflow_dict.get("current_phase"),
                "overall_progress_percent": workflow_dict.get("overall_progress_percent"),
                "latest_ingestion_event": latest_ingestion_event,
                "ingestion_cost": ingestion_cost_summary,
                "retrieval_cost": retrieval_cost_summary,
                "generation_cost": generation_cost_summary,
                "final_observability_summary": final_summary,
            },
        },
    )