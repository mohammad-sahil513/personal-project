from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
MODES = ("local_services", "local_api")


def utc_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def ensure_file(path_value: str, *, label: str) -> Path:
    path = Path(path_value).expanduser().resolve()
    if not path.is_file():
        raise SystemExit(f"[MANUAL][FAIL] {label} not found: {path}")
    return path


def infer_content_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@dataclass
class ManualRun:
    runner_name: str
    run_id: str
    run_dir: Path
    events_log: Path

    @classmethod
    def create(cls, *, runner_name: str, output_root: str) -> "ManualRun":
        root = Path(output_root).expanduser().resolve()
        run_id = f"{runner_name}_{utc_stamp()}_{uuid4().hex[:8]}"
        run_dir = root / runner_name / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        return cls(runner_name=runner_name, run_id=run_id, run_dir=run_dir, events_log=run_dir / "events.log")

    def log(self, message: str) -> None:
        line = f"{datetime.now(UTC).isoformat()} {message}"
        print(line)
        with self.events_log.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def write_stage_snapshot(
        self,
        *,
        stage_name: str,
        snapshot: dict[str, Any],
        extra: dict[str, Any] | None = None,
    ) -> None:
        stage_dir = self.run_dir / "stages" / stage_name
        write_json(stage_dir / "snapshot.json", snapshot)
        if extra:
            write_json(stage_dir / "extra.json", extra)
        report_lines = [
            f"# {stage_name} Manual Verification",
            "",
            f"- Runner: `{self.runner_name}`",
            f"- Stage: `{stage_name}`",
            f"- Captured At (UTC): `{datetime.now(UTC).isoformat()}`",
            f"- Snapshot File: `stages/{stage_name}/snapshot.json`",
        ]
        if extra:
            report_lines.append(f"- Extra File: `stages/{stage_name}/extra.json`")
        report_lines.append("")
        write_text(stage_dir / "stage_report.md", "\n".join(report_lines))

    def write_metadata(self, payload: dict[str, Any]) -> None:
        write_json(self.run_dir / "run_metadata.json", payload)


def add_common_args(parser: argparse.ArgumentParser, *, require_template: bool = False) -> None:
    parser.add_argument("--mode", choices=MODES, default="local_services")
    parser.add_argument("--document", required=False, help="Input document path")
    parser.add_argument("--template", required=require_template, help="Input template (.docx) path")
    parser.add_argument("--output-root", default="manual_testing/output")
    parser.add_argument("--base-url", default=os.getenv("STAGING_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--poll-interval-sec", type=float, default=5.0)
    parser.add_argument("--max-wait-sec", type=float, default=1800.0)


def api_json(resp: httpx.Response) -> dict[str, Any]:
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:1000]}")
    body = resp.json()
    if isinstance(body, dict) and not body.get("success", True):
        raise RuntimeError(f"API success=false: {body}")
    return body.get("data", body)


def poll_until(
    *,
    fetch_status: Any,
    is_done: Any,
    poll_interval_sec: float,
    max_wait_sec: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + max_wait_sec
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last = fetch_status()
        if is_done(last):
            return last
        time.sleep(poll_interval_sec)
    raise TimeoutError("Polling timeout reached")
