from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.modules.ingestion.observability.models import IngestionRunContext, StageObservation


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


class OfficialFileLogger:
    """
    Structured file logger for operational tracing.

    This logger intentionally records only safe metadata and stage/run metrics.
    It must not log raw request or content body data.
    """

    def __init__(self, *, log_path: Path) -> None:
        self._log_path = log_path

    def log_run_started(self, context: IngestionRunContext) -> None:
        self._write(
            event="run_started",
            run_id=context.run_id,
            file_name=context.file_name,
            content_type=context.content_type,
            file_size_bytes=context.file_size_bytes,
            started_at=context.started_at.isoformat(),
            log_mode=context.log_mode.value,
        )

    def log_stage_started(self, *, run_id: str, stage_name: str, safe_metadata: dict[str, Any]) -> None:
        self._write(
            event="stage_started",
            run_id=run_id,
            stage_name=stage_name,
            safe_metadata=safe_metadata,
        )

    def log_stage_completed(self, *, run_id: str, observation: StageObservation) -> None:
        self._write(
            event="stage_completed",
            run_id=run_id,
            stage_name=observation.stage_name,
            status=observation.status,
            started_at=observation.started_at.isoformat(),
            completed_at=observation.completed_at.isoformat() if observation.completed_at else None,
            duration_ms=observation.duration_ms,
            safe_metadata=observation.safe_metadata,
            usage_metrics=observation.usage_summary.metrics,
            warning_count=observation.warning_count,
        )

    def log_stage_failed(self, *, run_id: str, observation: StageObservation) -> None:
        self._write(
            event="stage_failed",
            run_id=run_id,
            stage_name=observation.stage_name,
            status=observation.status,
            started_at=observation.started_at.isoformat(),
            completed_at=observation.completed_at.isoformat() if observation.completed_at else None,
            duration_ms=observation.duration_ms,
            safe_metadata=observation.safe_metadata,
            usage_metrics=observation.usage_summary.metrics,
            warning_count=observation.warning_count,
            error_message=observation.error_message,
        )

    def log_run_completed(
        self,
        *,
        context: IngestionRunContext,
        final_status: str,
        stage_count: int,
    ) -> None:
        self._write(
            event="run_completed",
            run_id=context.run_id,
            final_status=final_status,
            stage_count=stage_count,
        )

    def log_run_failed(
        self,
        *,
        context: IngestionRunContext,
        error_message: str,
    ) -> None:
        self._write(
            event="run_failed",
            run_id=context.run_id,
            error_message=error_message,
        )

    def _write(self, **payload: Any) -> None:
        line = {
            "timestamp": _timestamp(),
            **payload,
        }
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, ensure_ascii=False) + "\n")


class DemoFileLogger:
    """
    Human-readable demo logger.

    The goal is to explain the pipeline flow step by step, without logging raw
    request or content data.
    """

    def __init__(self, *, log_path: Path) -> None:
        self._log_path = log_path

    def log_run_started(self, context: IngestionRunContext) -> None:
        self._write(
            f"[{_timestamp()}] RUN STARTED | run_id={context.run_id} | file={context.file_name} "
            f"| content_type={context.content_type} | file_size_bytes={context.file_size_bytes}"
        )

    def log_stage_started(self, *, run_id: str, stage_name: str, safe_metadata: dict[str, Any]) -> None:
        summary = self._format_safe_metadata(safe_metadata)
        self._write(
            f"[{_timestamp()}] STAGE STARTED | run_id={run_id} | stage={stage_name} | {summary}"
        )

    def log_stage_completed(self, *, run_id: str, observation: StageObservation) -> None:
        summary = self._format_safe_metadata(observation.safe_metadata)
        usage = self._format_usage(observation.usage_summary.metrics)
        duration_text = f"{observation.duration_ms:.3f}" if observation.duration_ms is not None else "0.000"

        self._write(
            f"[{_timestamp()}] STAGE COMPLETED | run_id={run_id} | stage={observation.stage_name} "
            f"| duration_ms={duration_text} "
            f"| warnings={observation.warning_count} | {summary} | usage={usage}"
        )

    def log_stage_failed(self, *, run_id: str, observation: StageObservation) -> None:
        summary = self._format_safe_metadata(observation.safe_metadata)
        usage = self._format_usage(observation.usage_summary.metrics)
        duration_text = f"{observation.duration_ms:.3f}" if observation.duration_ms is not None else "0.000"

        self._write(
            f"[{_timestamp()}] STAGE FAILED | run_id={run_id} | stage={observation.stage_name} "
            f"| duration_ms={duration_text} "
            f"| warnings={observation.warning_count} | {summary} | usage={usage} "
            f"| error={observation.error_message or 'unknown'}"
        )

    def log_run_completed(
        self,
        *,
        context: IngestionRunContext,
        final_status: str,
        stage_count: int,
    ) -> None:
        self._write(
            f"[{_timestamp()}] RUN COMPLETED | run_id={context.run_id} | final_status={final_status} "
            f"| stages_observed={stage_count}"
        )

    def log_run_failed(
        self,
        *,
        context: IngestionRunContext,
        error_message: str,
    ) -> None:
        self._write(
            f"[{_timestamp()}] RUN FAILED | run_id={context.run_id} | error={error_message}"
        )

    def _write(self, line: str) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._log_path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    @staticmethod
    def _format_safe_metadata(metadata: dict[str, Any]) -> str:
        if not metadata:
            return "safe_metadata=<none>"
        return "safe_metadata=" + ", ".join(f"{key}={value}" for key, value in metadata.items())

    @staticmethod
    def _format_usage(metrics: dict[str, Any]) -> str:
        if not metrics:
            return "<none>"
        return ", ".join(f"{key}={value}" for key, value in metrics.items())


class LoggerMultiplexer:
    """Routes events to official/demo loggers depending on the requested mode."""

    def __init__(
        self,
        *,
        official_logger: OfficialFileLogger | None = None,
        demo_logger: DemoFileLogger | None = None,
    ) -> None:
        self._official_logger = official_logger
        self._demo_logger = demo_logger

    def log_run_started(self, context: IngestionRunContext) -> None:
        if self._official_logger:
            self._official_logger.log_run_started(context)
        if self._demo_logger:
            self._demo_logger.log_run_started(context)

    def log_stage_started(self, *, run_id: str, stage_name: str, safe_metadata: dict[str, Any]) -> None:
        if self._official_logger:
            self._official_logger.log_stage_started(
                run_id=run_id,
                stage_name=stage_name,
                safe_metadata=safe_metadata,
            )
        if self._demo_logger:
            self._demo_logger.log_stage_started(
                run_id=run_id,
                stage_name=stage_name,
                safe_metadata=safe_metadata,
            )

    def log_stage_completed(self, *, run_id: str, observation: StageObservation) -> None:
        if self._official_logger:
            self._official_logger.log_stage_completed(run_id=run_id, observation=observation)
        if self._demo_logger:
            self._demo_logger.log_stage_completed(run_id=run_id, observation=observation)

    def log_stage_failed(self, *, run_id: str, observation: StageObservation) -> None:
        if self._official_logger:
            self._official_logger.log_stage_failed(run_id=run_id, observation=observation)
        if self._demo_logger:
            self._demo_logger.log_stage_failed(run_id=run_id, observation=observation)

    def log_run_completed(self, *, context: IngestionRunContext, final_status: str, stage_count: int) -> None:
        if self._official_logger:
            self._official_logger.log_run_completed(
                context=context,
                final_status=final_status,
                stage_count=stage_count,
            )
        if self._demo_logger:
            self._demo_logger.log_run_completed(
                context=context,
                final_status=final_status,
                stage_count=stage_count,
            )

    def log_run_failed(self, *, context: IngestionRunContext, error_message: str) -> None:
        if self._official_logger:
            self._official_logger.log_run_failed(context=context, error_message=error_message)
        if self._demo_logger:
            self._demo_logger.log_run_failed(context=context, error_message=error_message)