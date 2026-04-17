"""
Template Azure smoke runner.

Smoke flow:
1. compile custom DOCX template (deterministic + AI-assisted compiler)
2. extract layout manifest
3. build shell DOCX
4. persist local artifacts
5. optionally upload artifacts to Azure Blob Storage
6. record structured smoke summary + event log

Run example:
python -m backend.modules.template.scripts.run_template_azure_smoke ^
  --docx "C:\\path\\to\\custom_template.docx" ^
  --template-id custom_sdd ^
  --name "Custom SDD" ^
  --version 1.0.0 ^
  --upload-blob
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from backend.modules.template.compiler.ai_compiler import AICompiler
from backend.modules.template.compiler.azure_sk_structured_adapter import (
    AzureSemanticKernelStructuredAdapter,
)
from backend.modules.template.compiler.compiler_orchestrator import CompilerOrchestrator
from backend.modules.template.compiler.correction_loop import CorrectionLoop
from backend.modules.template.compiler.defaults_injector import DefaultsInjector
from backend.modules.template.compiler.docx_extractor import DocxExtractor
from backend.modules.template.compiler.heuristic_mapper import HeuristicMapper
from backend.modules.template.compiler.semantic_validator import SemanticValidator
from backend.modules.template.layout.layout_extractor import LayoutExtractor
from backend.modules.template.layout.shell_builder import ShellBuilder
from backend.modules.template.services.template_artifact_service import TemplateArtifactService
from backend.modules.template.services.template_blob_publisher_service import (
    TemplateBlobPublisherService,
)


@dataclass(frozen=True, slots=True)
class SmokeEvent:
    """One structured smoke event."""

    timestamp_utc: str
    event: str
    status: str
    details: dict


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _record_event(events: list[SmokeEvent], *, event: str, status: str, **details) -> None:
    events.append(
        SmokeEvent(
            timestamp_utc=_utc_now(),
            event=event,
            status=status,
            details=details,
        )
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_jsonl(path: Path, events: list[SmokeEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Template Azure smoke validation.")
    parser.add_argument("--docx", required=True, help="Path to the source custom template DOCX.")
    parser.add_argument("--template-id", required=True, help="Logical template ID.")
    parser.add_argument("--name", required=True, help="Human-readable template name.")
    parser.add_argument("--version", required=True, help="Template version string.")
    parser.add_argument(
        "--description",
        default=None,
        help="Optional template description.",
    )
    repo_root = Path(__file__).resolve().parents[2]

    parser.add_argument(
        "--project-root",
        default=str(repo_root),
        help="Project root path.",
    )
    parser.add_argument(
        "--artifact-root",
        default=str(repo_root / "artifacts"),
        help="Local artifact root path.",
    )
    parser.add_argument(
        "--heuristic-config",
        default=None,
        help="Optional override path for heuristic_patterns.yaml.",
    )
    parser.add_argument(
        "--upload-blob",
        action="store_true",
        help="Upload persisted artifacts to Azure Blob Storage after local persistence.",
    )
    parser.add_argument(
        "--blob-root-prefix",
        default="sahil_storage",
        help="Blob root prefix. Must remain under sahil_storage/ for this project.",
    )
    parser.add_argument(
        "--requirement-ids-filter-supported",
        action="store_true",
        help="Set this if deployed search schema already supports requirement_ids filtering.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    project_root = Path(args.project_root).resolve()
    artifact_root = Path(args.artifact_root).resolve()
    smoke_dir = artifact_root / "template" / "smoke" / args.template_id / args.version
    smoke_dir.mkdir(parents=True, exist_ok=True)

    events: list[SmokeEvent] = []
    summary_path = smoke_dir / "smoke_summary.json"
    events_path = smoke_dir / "smoke_events.jsonl"

    start_time = perf_counter()
    _record_event(
        events,
        event="template_smoke_start",
        status="started",
        docx=str(Path(args.docx).resolve()),
        template_id=args.template_id,
        template_version=args.version,
        upload_blob=args.upload_blob,
    )

    try:
        heuristic_config = (
            Path(args.heuristic_config).resolve()
            if args.heuristic_config is not None
            else project_root / "config" / "heuristic_patterns.yaml"
        )

        ai_adapter = AzureSemanticKernelStructuredAdapter(
            default_deployment_alias="gpt5mini",
        )
        correction_adapter = AzureSemanticKernelStructuredAdapter(
            default_deployment_alias="gpt5",
        )

        _record_event(
            events,
            event="azure_adapter_ready",
            status="ok",
            ai_compiler_default_deployment="gpt-5-mini",
            correction_default_deployment="gpt-5",
        )

        compiler = CompilerOrchestrator(
            docx_extractor=DocxExtractor(),
            heuristic_mapper=HeuristicMapper(
                project_root=project_root,
                config_path=heuristic_config,
            ),
            ai_compiler=AICompiler(
                project_root=project_root,
                sk_adapter=ai_adapter,
            ),
            defaults_injector=DefaultsInjector(),
            semantic_validator=SemanticValidator(),
            correction_loop=CorrectionLoop(
                project_root=project_root,
                sk_adapter=correction_adapter,
            ),
        )

        compile_result = compiler.compile_custom_template(
            docx_path=str(Path(args.docx).resolve()),
            template_id=args.template_id,
            name=args.name,
            version=args.version,
            description=args.description,
            requirement_ids_filter_supported=args.requirement_ids_filter_supported,
        )
        _record_event(
            events,
            event="template_compile_completed",
            status="ok",
            section_count=len(compile_result.template_definition.sections),
            semantic_is_valid=compile_result.semantic_validation_result.is_valid,
            ai_suggestion_count=len(compile_result.ai_suggestions),
            correction_applied=compile_result.correction_applied,
        )

        layout_manifest = LayoutExtractor().extract_layout(
            docx_path=args.docx,
            template_id=args.template_id,
            version=args.version,
        )
        _record_event(
            events,
            event="layout_extraction_completed",
            status="ok",
            anchor_count=len(layout_manifest.anchors),
            style_count=len(layout_manifest.styles),
            table_count=len(layout_manifest.tables),
            section_count=layout_manifest.section_count,
        )

        shell_result = ShellBuilder(
            output_root=artifact_root / "template" / "shells"
        ).build_shell(
            source_docx_path=args.docx,
            template_id=args.template_id,
            version=args.version,
        )
        _record_event(
            events,
            event="shell_build_completed",
            status="ok",
            shell_docx_path=str(shell_result.shell_docx_path),
            cleared_paragraph_count=shell_result.cleared_paragraph_count,
            cleared_table_cell_count=shell_result.cleared_table_cell_count,
        )

        persisted = TemplateArtifactService(
            artifact_root=artifact_root
        ).persist(
            template_definition=compile_result.template_definition,
            layout_manifest=layout_manifest,
            shell_docx_path=shell_result.shell_docx_path,
        )
        _record_event(
            events,
            event="local_artifact_persist_completed",
            status="ok",
            template_json_path=str(persisted.template_json_path),
            layout_manifest_path=str(persisted.layout_manifest_path) if persisted.layout_manifest_path else None,
            shell_docx_path=str(persisted.shell_docx_path) if persisted.shell_docx_path else None,
            compiled_artifact_manifest_path=str(persisted.compiled_artifact_manifest_path),
        )

        blob_artifacts: dict[str, dict] = {}
        if args.upload_blob:
            publisher = TemplateBlobPublisherService(
                root_prefix=args.blob_root_prefix,
            )
            local_artifacts = {
                "template_json": persisted.template_json_path,
                "compiled_artifact_manifest": persisted.compiled_artifact_manifest_path,
            }
            if persisted.layout_manifest_path is not None:
                local_artifacts["layout_manifest"] = persisted.layout_manifest_path
            if persisted.shell_docx_path is not None:
                local_artifacts["shell_docx"] = persisted.shell_docx_path

            published = publisher.publish_artifacts(
                template_id=args.template_id,
                version=args.version,
                artifacts=local_artifacts,
                subfolder="template/custom",
            )
            blob_artifacts = {
                key: {
                    "blob_path": value.blob_path,
                    "blob_url": value.blob_url,
                }
                for key, value in published.items()
            }
            _record_event(
                events,
                event="blob_publish_completed",
                status="ok",
                artifact_count=len(blob_artifacts),
                artifacts=blob_artifacts,
            )

        duration_ms = round((perf_counter() - start_time) * 1000, 2)
        summary = {
            "status": "success",
            "started_at_utc": events[0].timestamp_utc,
            "finished_at_utc": _utc_now(),
            "duration_ms": duration_ms,
            "template_id": args.template_id,
            "template_version": args.version,
            "source_docx_path": str(Path(args.docx).resolve()),
            "compile": {
                "section_count": len(compile_result.template_definition.sections),
                "semantic_is_valid": compile_result.semantic_validation_result.is_valid,
                "ai_suggestion_count": len(compile_result.ai_suggestions),
                "correction_applied": compile_result.correction_applied,
                "correction_warnings": list(compile_result.correction_warnings),
            },
            "layout": {
                "section_count": layout_manifest.section_count,
                "anchor_count": len(layout_manifest.anchors),
                "style_count": len(layout_manifest.styles),
                "table_count": len(layout_manifest.tables),
            },
            "local_artifacts": {
                "template_json_path": str(persisted.template_json_path),
                "layout_manifest_path": str(persisted.layout_manifest_path) if persisted.layout_manifest_path else None,
                "shell_docx_path": str(persisted.shell_docx_path) if persisted.shell_docx_path else None,
                "compiled_artifact_manifest_path": str(persisted.compiled_artifact_manifest_path),
            },
            "blob_artifacts": blob_artifacts,
        }

        _record_event(
            events,
            event="template_smoke_completed",
            status="success",
            duration_ms=duration_ms,
            summary_path=str(summary_path),
            events_path=str(events_path),
        )
        _write_json(summary_path, summary)
        _write_jsonl(events_path, events)

        print(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"\nSmoke summary written to: {summary_path}")
        print(f"Smoke events written to:  {events_path}")
        return 0

    except Exception as exc:  # noqa: BLE001 - explicit smoke-run failure capture
        duration_ms = round((perf_counter() - start_time) * 1000, 2)
        failure_summary = {
            "status": "failed",
            "started_at_utc": events[0].timestamp_utc if events else _utc_now(),
            "finished_at_utc": _utc_now(),
            "duration_ms": duration_ms,
            "template_id": args.template_id,
            "template_version": args.version,
            "source_docx_path": str(Path(args.docx).resolve()),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc(),
        }

        _record_event(
            events,
            event="template_smoke_failed",
            status="failed",
            error_type=type(exc).__name__,
            error_message=str(exc),
            duration_ms=duration_ms,
        )
        _write_json(summary_path, failure_summary)
        _write_jsonl(events_path, events)

        print(json.dumps(failure_summary, indent=2, ensure_ascii=False), file=sys.stderr)
        print(f"\nSmoke summary written to: {summary_path}", file=sys.stderr)
        print(f"Smoke events written to:  {events_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())