#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.application.services.document_service import DocumentService
from backend.application.services.template_app_service import TemplateAppService
from backend.application.services.template_compile_service import TemplateCompileService
from backend.application.services.workflow_executor_service import WorkflowExecutorService
from backend.application.services.workflow_service import WorkflowService
from backend.manual_testing.common import (
    ManualRun,
    add_common_args,
    api_json,
    ensure_file,
    infer_content_type,
    poll_until,
)
from backend.pipeline.planners.progress_planner import WORKFLOW_PHASE_ORDER


def _phase_reached(current_phase: str, target: str) -> bool:
    try:
        return WORKFLOW_PHASE_ORDER.index(current_phase) >= WORKFLOW_PHASE_ORDER.index(target)
    except ValueError:
        return False


async def _local_services(args: argparse.Namespace, run: ManualRun) -> None:
    if not args.document or not args.template:
        raise SystemExit("--document and --template are required for local_services mode")
    doc_path = ensure_file(args.document, label="Document")
    tpl_path = ensure_file(args.template, label="Template")

    doc_service = DocumentService()
    tpl_service = TemplateAppService()
    wf_service = WorkflowService()
    executor = WorkflowExecutorService(workflow_service=wf_service)

    doc = doc_service.create_document(
        filename=doc_path.name,
        content_type=infer_content_type(doc_path),
        size=len(doc_path.read_bytes()),
        file_bytes=doc_path.read_bytes(),
    )
    tpl = tpl_service.create_template(
        filename=tpl_path.name,
        template_type="SDLC",
        version="manual-test",
        file_bytes=tpl_path.read_bytes(),
    )
    await TemplateCompileService(template_app_service=tpl_service).execute_compile(tpl.template_id)
    wf = wf_service.create_workflow(document_id=doc.document_id, template_id=tpl.template_id)
    await executor.build_and_attach_section_plan(wf.workflow_run_id)
    latest = wf_service.get_workflow(wf.workflow_run_id).to_dict()
    run.log(f"[SECTION_PLANNING] workflow_run_id={wf.workflow_run_id}")
    run.write_stage_snapshot(stage_name="SECTION_PLANNING", snapshot=latest, extra={"section_plan": latest.get("section_plan")})
    run.write_metadata(
        {
            "runner": "run_section_planning_manual.py",
            "mode": "local_services",
            "workflow_run_id": wf.workflow_run_id,
            "document_id": doc.document_id,
            "template_id": tpl.template_id,
            "input_document": str(doc_path),
            "input_template": str(tpl_path),
        }
    )


async def _local_api(args: argparse.Namespace, run: ManualRun) -> None:
    if not args.document or not args.template:
        raise SystemExit("--document and --template are required for local_api mode")
    doc_path = ensure_file(args.document, label="Document")
    tpl_path = ensure_file(args.template, label="Template")
    base = args.base_url.rstrip("/")
    api = f"{base}/api"
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
        api_json(client.get(f"{api}/health"))
        doc = api_json(
            client.post(
                f"{api}/documents/upload",
                files={"file": (doc_path.name, doc_path.read_bytes(), infer_content_type(doc_path))},
            )
        )
        tpl = api_json(
            client.post(
                f"{api}/templates/upload",
                files={"file": (tpl_path.name, tpl_path.read_bytes(), infer_content_type(tpl_path))},
                data={"template_type": "SDLC", "version": "manual-test"},
            )
        )
        template_id = tpl["template_id"]
        api_json(client.post(f"{api}/templates/{template_id}/compile", json={"use_ai_assist": True, "publish_artifacts": False}))
        poll_until(
            fetch_status=lambda: api_json(client.get(f"{api}/templates/{template_id}/compile-status")),
            is_done=lambda status: str(status.get("status", "")) in {"COMPILED", "FAILED"},
            poll_interval_sec=args.poll_interval_sec,
            max_wait_sec=args.max_wait_sec,
        )
        wf = api_json(
            client.post(
                f"{api}/workflow-runs",
                json={"document_id": doc["document_id"], "template_id": template_id, "start_immediately": True},
            )
        )
        workflow_run_id = wf["workflow_run_id"]
        latest = poll_until(
            fetch_status=lambda: api_json(client.get(f"{api}/workflow-runs/{workflow_run_id}")),
            is_done=lambda body: _phase_reached(str(body.get("current_phase", "")), "SECTION_PLANNING")
            or str(body.get("status", "")) in {"FAILED", "COMPLETED"},
            poll_interval_sec=args.poll_interval_sec,
            max_wait_sec=args.max_wait_sec,
        )
        sections = api_json(client.get(f"{api}/workflow-runs/{workflow_run_id}/sections"))
        run.write_stage_snapshot(stage_name="SECTION_PLANNING", snapshot=latest, extra={"sections": sections})
        run.write_metadata(
            {
                "runner": "run_section_planning_manual.py",
                "mode": "local_api",
                "base_url": base,
                "workflow_run_id": workflow_run_id,
                "document_id": doc["document_id"],
                "template_id": template_id,
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual section-planning stage runner")
    add_common_args(parser, require_template=False)
    args = parser.parse_args()
    run = ManualRun.create(runner_name="run_section_planning_manual", output_root=args.output_root)
    if args.mode == "local_api":
        return asyncio.run(_local_api(args, run)) or 0
    return asyncio.run(_local_services(args, run)) or 0


if __name__ == "__main__":
    raise SystemExit(main())
