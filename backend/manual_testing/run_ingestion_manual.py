#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.application.services.document_service import DocumentService
from backend.core.ids import generate_execution_id
from backend.manual_testing.common import (
    ManualRun,
    add_common_args,
    api_json,
    ensure_file,
    infer_content_type,
)
from backend.modules.ingestion.live_wiring import build_ingestion_runtime


async def _run_local_services(args: argparse.Namespace, run: ManualRun) -> None:
    doc_path = ensure_file(args.document, label="Document")
    file_bytes = doc_path.read_bytes()
    content_type = infer_content_type(doc_path)

    doc_service = DocumentService()
    created_doc = doc_service.create_document(
        filename=doc_path.name,
        content_type=content_type,
        size=len(file_bytes),
        file_bytes=file_bytes,
    )
    workflow_run_id = f"wf_manual_{uuid4().hex[:12]}"
    ingestion_execution_id = generate_execution_id()
    runtime = build_ingestion_runtime()

    run.log(f"[INGESTION] Starting local_services run workflow_run_id={workflow_run_id}")
    result = await runtime.run_ingestion(
        workflow_run_id=workflow_run_id,
        document_id=created_doc.document_id,
        ingestion_execution_id=ingestion_execution_id,
    )
    run.write_stage_snapshot(stage_name="INGESTION", snapshot=result)
    run.write_metadata(
        {
            "runner": "run_ingestion_manual.py",
            "mode": "local_services",
            "run_id": run.run_id,
            "workflow_run_id": workflow_run_id,
            "ingestion_execution_id": ingestion_execution_id,
            "document_id": created_doc.document_id,
            "input_document": str(doc_path),
            "logs_root": str((runtime.logs_root / workflow_run_id).resolve()),
            "status": result.get("status"),
        }
    )


async def _run_local_api(args: argparse.Namespace, run: ManualRun) -> None:
    doc_path = ensure_file(args.document, label="Document")
    base = args.base_url.rstrip("/")
    api = f"{base}/api"
    run.log(f"[INGESTION] Starting local_api run base_url={base}")

    with httpx.Client(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
        api_json(client.get(f"{api}/health"))
        uploaded = api_json(
            client.post(
                f"{api}/documents/upload",
                files={"file": (doc_path.name, doc_path.read_bytes(), infer_content_type(doc_path))},
            )
        )
        document_id = uploaded["document_id"]
        run.log(f"[INGESTION] Uploaded document_id={document_id}")
        run.write_stage_snapshot(stage_name="INGESTION", snapshot=uploaded)
        run.write_metadata(
            {
                "runner": "run_ingestion_manual.py",
                "mode": "local_api",
                "run_id": run.run_id,
                "document_id": document_id,
                "input_document": str(doc_path),
                "base_url": base,
                "note": "API-only ingestion runner validates upload path; full ingestion executes inside workflow runner.",
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual ingestion stage runner")
    add_common_args(parser)
    args = parser.parse_args()
    if not args.document:
        raise SystemExit("--document is required")
    run = ManualRun.create(runner_name="run_ingestion_manual", output_root=args.output_root)
    if args.mode == "local_api":
        return asyncio.run(_run_local_api(args, run)) or 0
    return asyncio.run(_run_local_services(args, run)) or 0


if __name__ == "__main__":
    raise SystemExit(main())
