from __future__ import annotations


import argparse
import asyncio
import mimetypes
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path



from backend.modules.ingestion.contracts.stage_1_contracts import Stage1Input
from backend.modules.ingestion.observability.artifact_store import LocalArtifactStore
from backend.modules.ingestion.observability.loggers import (
    DemoFileLogger,
    LoggerMultiplexer,
    OfficialFileLogger,
)
from backend.modules.ingestion.observability.models import (
    IngestionRunContext,
    LogMode,
    RunPaths,
)
from backend.modules.ingestion.observability.observer import FileIngestionObserver
from backend.modules.ingestion.observability.observed_runners import (
    ObservedStageRunner,
    default_safe_metadata_builder,
)
from backend.pipeline.bootstrap.ingestion_bootstrap import (
    build_ingestion_stage_runners,
    build_observed_orchestrator,
)
from backend.pipeline.orchestrators.ingestion_orchestrator import IngestionRunConfig


# REPO_ROOT = Path(__file__).resolve().parents[2]
# if str(REPO_ROOT) not in sys.path:
#     sys.path.insert(0, str(REPO_ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the ingestion pipeline with file-based observability.")
    parser.add_argument("--file", required=True, help="Path to the BRD file to ingest.")
    parser.add_argument(
        "--content-type",
        default=None,
        help="Optional explicit content type. If omitted, it is guessed from the file extension.",
    )
    parser.add_argument(
        "--log-mode",
        choices=[mode.value for mode in LogMode],
        default=LogMode.BOTH.value,
        help="Which log file(s) to generate.",
    )
    parser.add_argument(
        "--output-root",
        default="observability",
        help="Root directory where logs and local artifacts will be written.",
    )
    parser.add_argument(
        "--repo-root",
        default=".ingestion_runtime",
        help="Local repository directory for ingestion job state.",
    )
    parser.add_argument(
        "--allowlist-email",
        action="append",
        default=[],
        help="Allowlisted system mailbox value for Stage 3. Can be repeated.",
    )
    parser.add_argument(
        "--disable-pii",
        action="store_true",
        help="Disable Stage 3 masking/classification.",
    )
    parser.add_argument(
        "--max-vision-calls",
        type=int,
        default=10,
        help="Stage 5 max vision calls per document.",
    )
    return parser.parse_args()


def guess_content_type(file_path: Path, explicit_content_type: str | None) -> str:
    if explicit_content_type:
        return explicit_content_type

    guessed = mimetypes.guess_type(str(file_path))[0]
    if guessed:
        return guessed

    # Reasonable default fallback for unknown file types
    return "application/octet-stream"


def build_run_paths(*, output_root: Path, run_id: str) -> RunPaths:
    run_root = output_root / "logs" / "ingestion" / run_id
    artifacts_root = output_root / "artifacts" / "ingestion" / run_id
    return RunPaths(
        root_dir=output_root,
        logs_dir=run_root,
        artifacts_dir=artifacts_root,
        official_log_path=run_root / "official.log",
        demo_log_path=run_root / "demo.log",
    )


def build_logger(mode: LogMode, paths: RunPaths) -> LoggerMultiplexer:
    official_logger = OfficialFileLogger(log_path=paths.official_log_path) if mode in {LogMode.OFFICIAL, LogMode.BOTH} else None
    demo_logger = DemoFileLogger(log_path=paths.demo_log_path) if mode in {LogMode.DEMO, LogMode.BOTH} else None
    return LoggerMultiplexer(
        official_logger=official_logger,
        demo_logger=demo_logger,
    )


async def main() -> int:
    args = parse_args()

    file_path = Path(args.file).expanduser().resolve()
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    file_bytes = file_path.read_bytes()
    if not file_bytes:
        raise ValueError(f"Input file is empty: {file_path}")

    log_mode = LogMode(args.log_mode)
    run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    output_root = Path(args.output_root).resolve()
    run_paths = build_run_paths(output_root=output_root, run_id=run_id)

    context = IngestionRunContext(
        run_id=run_id,
        file_name=file_path.name,
        content_type=guess_content_type(file_path, args.content_type),
        file_size_bytes=len(file_bytes),
        log_mode=log_mode,
        paths=run_paths,
    )

    logger = build_logger(log_mode, run_paths)
    artifact_store = LocalArtifactStore(artifacts_root=run_paths.artifacts_dir)
    observer = FileIngestionObserver(
        logger=logger,
        artifact_store=artifact_store,
    )

    observer.on_run_started(context=context)

    repository, stage_runners = build_ingestion_stage_runners(repo_dir=Path(args.repo_root).resolve())
    await repository.initialize()

    observed_runners = {
        stage_key: ObservedStageRunner(
            stage_name=stage_key.upper(),
            inner_runner=runner,
            observer=observer,
            safe_metadata_builder=default_safe_metadata_builder,
            context=context,
        )
        for stage_key, runner in stage_runners.items()
    }

    orchestrator = build_observed_orchestrator(stage_runners=observed_runners)

    stage_1_input = Stage1Input(
        file_name=file_path.name,
        content_type=context.content_type,
        file_bytes=file_bytes,
        initiated_by="scripts/run_ingestion.py",
    )

    try:
        result = await orchestrator.run(
            stage_1_input=stage_1_input,
            config=IngestionRunConfig(
                pii_enabled=not args.disable_pii,
                system_email_allowlist=args.allowlist_email,
                max_vision_calls=args.max_vision_calls,
                short_circuit_on_duplicate=False,
            ),
        )
    except Exception as exc:
        observer.on_run_failed(context=context, error_message=str(exc))
        # Minimal terminal output only — logs remain in files.
        print(f"INGESTION FAILED | run_id={run_id} | review: {run_paths.logs_dir}", file=sys.stderr)
        return 1

    observer.on_run_completed(
        context=context,
        final_status=result.status.value,
        stage_count=9,
    )

    # Save final pipeline result locally for review.
    artifact_store.store_stage_output(stage_name="FINAL_PIPELINE_RESULT", output_model=result)

    # Minimal terminal output only — logs/artifacts remain file-based.
    print(f"INGESTION COMPLETED | run_id={run_id} | review logs: {run_paths.logs_dir}")
    print(f"ARTIFACT SNAPSHOTS | {run_paths.artifacts_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))