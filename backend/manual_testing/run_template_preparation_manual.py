#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.application.services.template_app_service import TemplateAppService
from backend.application.services.template_compile_service import TemplateCompileService
from backend.manual_testing.common import (
    ManualRun,
    add_common_args,
    api_json,
    ensure_file,
    infer_content_type,
    poll_until,
)


async def _local_services(args: argparse.Namespace, run: ManualRun) -> None:
    template_path = ensure_file(args.template, label="Template")
    tpl_service = TemplateAppService()
    tpl = tpl_service.create_template(
        filename=template_path.name,
        template_type="SDLC",
        version="manual-test",
        file_bytes=template_path.read_bytes(),
    )
    compile_service = TemplateCompileService(template_app_service=tpl_service)
    result = await compile_service.execute_compile(tpl.template_id)
    run.log(f"[TEMPLATE_PREPARATION] template_id={tpl.template_id} status={result.get('status')}")
    run.write_stage_snapshot(stage_name="TEMPLATE_PREPARATION", snapshot=result)
    run.write_metadata(
        {
            "runner": "run_template_preparation_manual.py",
            "mode": "local_services",
            "template_id": tpl.template_id,
            "input_template": str(template_path),
            "status": result.get("status"),
        }
    )


async def _local_api(args: argparse.Namespace, run: ManualRun) -> None:
    template_path = ensure_file(args.template, label="Template")
    base = args.base_url.rstrip("/")
    api = f"{base}/api"
    with httpx.Client(timeout=httpx.Timeout(120.0, connect=30.0)) as client:
        api_json(client.get(f"{api}/health"))
        uploaded = api_json(
            client.post(
                f"{api}/templates/upload",
                files={"file": (template_path.name, template_path.read_bytes(), infer_content_type(template_path))},
                data={"template_type": "SDLC", "version": "manual-test"},
            )
        )
        template_id = uploaded["template_id"]
        run.log(f"[TEMPLATE_PREPARATION] uploaded template_id={template_id}")
        api_json(
            client.post(
                f"{api}/templates/{template_id}/compile",
                json={"use_ai_assist": True, "publish_artifacts": False},
            )
        )
        final = poll_until(
            fetch_status=lambda: api_json(client.get(f"{api}/templates/{template_id}/compile-status")),
            is_done=lambda status: str(status.get("status", "")) in {"COMPILED", "FAILED"},
            poll_interval_sec=args.poll_interval_sec,
            max_wait_sec=args.max_wait_sec,
        )
        run.write_stage_snapshot(stage_name="TEMPLATE_PREPARATION", snapshot=final, extra={"upload": uploaded})
        run.write_metadata(
            {
                "runner": "run_template_preparation_manual.py",
                "mode": "local_api",
                "base_url": base,
                "template_id": template_id,
                "input_template": str(template_path),
                "status": final.get("status"),
            }
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Manual template preparation stage runner")
    add_common_args(parser, require_template=True)
    args = parser.parse_args()
    run = ManualRun.create(runner_name="run_template_preparation_manual", output_root=args.output_root)
    if args.mode == "local_api":
        return asyncio.run(_local_api(args, run)) or 0
    return asyncio.run(_local_services(args, run)) or 0


if __name__ == "__main__":
    raise SystemExit(main())
