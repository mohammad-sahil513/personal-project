#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.application.services.document_service import DocumentService
from backend.application.services.output_service import OutputService
from backend.application.services.template_app_service import TemplateAppService
from backend.application.services.template_compile_service import TemplateCompileService
from backend.application.services.workflow_executor_service import WorkflowExecutorService
from backend.application.services.workflow_section_retrieval_service import WorkflowSectionRetrievalService
from backend.application.services.workflow_service import WorkflowService
from backend.manual_testing.common import (
    ManualRun,
    add_common_args,
    api_json,
    ensure_file,
    infer_content_type,
    poll_until,
    write_json,
)


async def _local_services(args: argparse.Namespace, run: ManualRun) -> None:
    if not args.document or not args.template:
        raise SystemExit("--document and --template are required")
    doc_path = ensure_file(args.document, label="Document")
    tpl_path = ensure_file(args.template, label="Template")
    doc_service = DocumentService()
    tpl_service = TemplateAppService()
    wf_service = WorkflowService()
    executor = WorkflowExecutorService(workflow_service=wf_service)
    retrieval_service = WorkflowSectionRetrievalService()

    doc = doc_service.create_document(filename=doc_path.name, content_type=infer_content_type(doc_path), size=len(doc_path.read_bytes()), file_bytes=doc_path.read_bytes())
    run.write_stage_snapshot(stage_name="INPUT_PREPARATION", snapshot=doc.to_dict())
    tpl = tpl_service.create_template(filename=tpl_path.name, template_type="SDLC", version="manual-test", file_bytes=tpl_path.read_bytes())
    compiled = await TemplateCompileService(template_app_service=tpl_service).execute_compile(tpl.template_id)
    run.write_stage_snapshot(stage_name="TEMPLATE_PREPARATION", snapshot=compiled)

    wf = wf_service.create_workflow(document_id=doc.document_id, template_id=tpl.template_id)
    await executor.execute_workflow_skeleton(wf.workflow_run_id)
    run.write_stage_snapshot(stage_name="INGESTION", snapshot=wf_service.get_workflow(wf.workflow_run_id).to_dict())
    await executor.build_and_attach_section_plan(wf.workflow_run_id)
    run.write_stage_snapshot(stage_name="SECTION_PLANNING", snapshot=wf_service.get_workflow(wf.workflow_run_id).to_dict())
    await executor.initialize_section_progress(wf.workflow_run_id)
    current = wf_service.get_workflow(wf.workflow_run_id)
    retrieval_results = await retrieval_service.run_retrieval_for_workflow(
        section_plan=current.section_plan,
        workflow_run_id=wf.workflow_run_id,
        document_id=doc.document_id,
        template_id=tpl.template_id,
    )
    wf_service.attach_section_retrieval_results(wf.workflow_run_id, section_retrieval_results=retrieval_results)
    run.write_stage_snapshot(stage_name="RETRIEVAL", snapshot=wf_service.get_workflow(wf.workflow_run_id).to_dict(), extra={"retrieval_results": retrieval_results})
    await executor.run_section_generation(wf.workflow_run_id)
    run.write_stage_snapshot(stage_name="GENERATION", snapshot=wf_service.get_workflow(wf.workflow_run_id).to_dict())
    await executor.assemble_generated_sections(wf.workflow_run_id)
    run.write_stage_snapshot(stage_name="ASSEMBLY_VALIDATION", snapshot=wf_service.get_workflow(wf.workflow_run_id).to_dict())
    await executor.prepare_output_export(wf.workflow_run_id)
    await executor.render_and_finalize_output(wf.workflow_run_id)
    final = wf_service.get_workflow(wf.workflow_run_id).to_dict()
    run.write_stage_snapshot(stage_name="RENDER_EXPORT", snapshot=final)
    output_id = final.get("output_id")
    if output_id:
        output = OutputService().get_output(output_id).to_dict()
        artifact = output.get("artifact_path")
        if artifact and Path(artifact).exists():
            (run.run_dir / "final_output.docx").write_bytes(Path(artifact).read_bytes())
    write_json(run.run_dir / "workflow_final_snapshot.json", final)
    run.write_metadata(
        {
            "runner": "run_workflow_stagewise_manual.py",
            "mode": "local_services",
            "workflow_run_id": wf.workflow_run_id,
            "document_id": doc.document_id,
            "template_id": tpl.template_id,
            "output_id": final.get("output_id"),
        }
    )


async def _local_api(args: argparse.Namespace, run: ManualRun) -> None:
    if not args.document or not args.template:
        raise SystemExit("--document and --template are required")
    doc_path = ensure_file(args.document, label="Document")
    tpl_path = ensure_file(args.template, label="Template")
    base_url = args.base_url.rstrip("/")
    api = f"{base_url}/api"
    timeout = httpx.Timeout(120.0, connect=30.0)
    with httpx.Client(timeout=timeout) as client:
        api_json(client.get(f"{api}/health"))
        uploaded_doc = api_json(client.post(f"{api}/documents/upload", files={"file": (doc_path.name, doc_path.read_bytes(), infer_content_type(doc_path))}))
        run.write_stage_snapshot(stage_name="INPUT_PREPARATION", snapshot=uploaded_doc)
        uploaded_tpl = api_json(
            client.post(
                f"{api}/templates/upload",
                files={"file": (tpl_path.name, tpl_path.read_bytes(), infer_content_type(tpl_path))},
                data={"template_type": "SDLC", "version": "manual-test"},
            )
        )
        template_id = uploaded_tpl["template_id"]
        api_json(client.post(f"{api}/templates/{template_id}/compile", json={"use_ai_assist": True, "publish_artifacts": False}))
        template_final = poll_until(
            fetch_status=lambda: api_json(client.get(f"{api}/templates/{template_id}/compile-status")),
            is_done=lambda status: str(status.get("status", "")) in {"COMPILED", "FAILED"},
            poll_interval_sec=args.poll_interval_sec,
            max_wait_sec=args.max_wait_sec,
        )
        run.write_stage_snapshot(stage_name="TEMPLATE_PREPARATION", snapshot=template_final)
        workflow_data = api_json(client.post(f"{api}/workflow-runs", json={"document_id": uploaded_doc["document_id"], "template_id": template_id, "start_immediately": True}))
        workflow_run_id = workflow_data["workflow_run_id"]
        last_phase = None
        last_status = None
        latest = {}
        deadline = time.monotonic() + args.max_wait_sec
        while time.monotonic() < deadline:
            latest = api_json(client.get(f"{api}/workflow-runs/{workflow_run_id}"))
            phase = str(latest.get("current_phase", "UNKNOWN"))
            status = str(latest.get("status", "UNKNOWN"))
            if phase != last_phase or status != last_status:
                run.write_stage_snapshot(stage_name=phase, snapshot=latest)
                last_phase = phase
                last_status = status
            if status in {"COMPLETED", "FAILED"}:
                break
            time.sleep(args.poll_interval_sec)
        write_json(run.run_dir / "workflow_final_snapshot.json", latest)
        if latest.get("output_id"):
            out = client.get(f"{api}/outputs/{latest['output_id']}/download", follow_redirects=True)
            if out.status_code == 200:
                (run.run_dir / "final_output.docx").write_bytes(out.content)
        run.write_metadata(
            {
                "runner": "run_workflow_stagewise_manual.py",
                "mode": "local_api",
                "workflow_run_id": workflow_run_id,
                "document_id": uploaded_doc["document_id"],
                "template_id": template_id,
                "output_id": latest.get("output_id"),
                "base_url": base_url,
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual full workflow stage-wise runner")
    add_common_args(parser, require_template=True)
    args = parser.parse_args()
    run = ManualRun.create(runner_name="run_workflow_stagewise_manual", output_root=args.output_root)
    if args.mode == "local_api":
        return asyncio.run(_local_api(args, run)) or 0
    return asyncio.run(_local_services(args, run)) or 0


if __name__ == "__main__":
    raise SystemExit(main())
