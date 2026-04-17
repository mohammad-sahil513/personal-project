from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from backend.modules.ingestion.observability.artifact_store import LocalArtifactStore
from backend.modules.ingestion.observability.loggers import LoggerMultiplexer
from backend.modules.ingestion.observability.models import (
    IngestionRunContext,
    StageObservation,
    StageUsageSummary,
)
from backend.modules.observability.services.cost_aggregation_service import (
    CostAggregationService,
)
from backend.modules.observability.services.cost_estimator_service import (
    CostEstimatorService,
)


class IngestionObserverProtocol(Protocol):
    def on_run_started(self, *, context: IngestionRunContext) -> None: ...
    def on_stage_started(self, *, context: IngestionRunContext, stage_name: str, safe_metadata: dict[str, Any]) -> None: ...
    def on_stage_completed(
        self,
        *,
        context: IngestionRunContext,
        stage_name: str,
        started_at: datetime,
        output_model: Any,
        safe_metadata: dict[str, Any],
    ) -> None: ...
    def on_stage_failed(
        self,
        *,
        context: IngestionRunContext,
        stage_name: str,
        started_at: datetime,
        error: Exception,
        safe_metadata: dict[str, Any],
    ) -> None: ...
    def on_run_completed(self, *, context: IngestionRunContext, final_status: str, stage_count: int) -> None: ...
    def on_run_failed(self, *, context: IngestionRunContext, error_message: str) -> None: ...


class FileIngestionObserver:
    """
    Observability bridge that writes:
    - official log file
    - demo log file
    - local stage artifact snapshots
    """

    def __init__(
        self,
        *,
        logger: LoggerMultiplexer,
        artifact_store: LocalArtifactStore,
        cost_estimator_service: CostEstimatorService | None = None,
        cost_aggregation_service: CostAggregationService | None = None,
    ) -> None:
        self._logger = logger
        self._artifact_store = artifact_store
        self._cost_estimator_service = cost_estimator_service
        self._cost_aggregation_service = cost_aggregation_service

    def on_run_started(self, *, context: IngestionRunContext) -> None:
        self._logger.log_run_started(context)

    def on_stage_started(self, *, context: IngestionRunContext, stage_name: str, safe_metadata: dict[str, Any]) -> None:
        self._logger.log_stage_started(
            run_id=context.run_id,
            stage_name=stage_name,
            safe_metadata=safe_metadata,
        )

    def on_stage_completed(
        self,
        *,
        context: IngestionRunContext,
        stage_name: str,
        started_at: datetime,
        output_model: Any,
        safe_metadata: dict[str, Any],
    ) -> None:
        completed_at = datetime.now(UTC)
        duration_ms = (completed_at - started_at).total_seconds() * 1000.0

        self._artifact_store.store_stage_output(
            stage_name=stage_name,
            output_model=output_model,
        )
        usage_metrics = self._extract_usage_metrics(output_model)
        stage_cost = self._estimate_stage_cost(
            context=context,
            stage_name=stage_name,
            usage_metrics=usage_metrics,
        )
        enriched_safe_metadata = dict(safe_metadata)
        if stage_cost:
            enriched_safe_metadata["cost"] = stage_cost

        observation = StageObservation(
            stage_name=stage_name,
            status="COMPLETED",
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(duration_ms, 3),
            safe_metadata=enriched_safe_metadata,
            usage_summary=StageUsageSummary(metrics=usage_metrics),
            warning_count=self._extract_warning_count(output_model),
        )
        self._logger.log_stage_completed(run_id=context.run_id, observation=observation)

    def on_stage_failed(
        self,
        *,
        context: IngestionRunContext,
        stage_name: str,
        started_at: datetime,
        error: Exception,
        safe_metadata: dict[str, Any],
    ) -> None:
        completed_at = datetime.now(UTC)
        duration_ms = (completed_at - started_at).total_seconds() * 1000.0
        observation = StageObservation(
            stage_name=stage_name,
            status="FAILED",
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=round(duration_ms, 3),
            safe_metadata=safe_metadata,
            usage_summary=StageUsageSummary(metrics={}),
            warning_count=0,
            error_message=str(error),
        )
        self._logger.log_stage_failed(run_id=context.run_id, observation=observation)

    def on_run_completed(self, *, context: IngestionRunContext, final_status: str, stage_count: int) -> None:
        self._logger.log_run_completed(context=context, final_status=final_status, stage_count=stage_count)

    def on_run_failed(self, *, context: IngestionRunContext, error_message: str) -> None:
        self._logger.log_run_failed(context=context, error_message=error_message)

    @staticmethod
    def _extract_warning_count(output_model: Any) -> int:
        warnings = getattr(output_model, "warnings", None)
        if isinstance(warnings, list):
            return len(warnings)
        return 0

    @staticmethod
    def _extract_usage_metrics(output_model: Any) -> dict[str, Any]:
        """
        Build a usage-style summary from the stage output model.

        This is intentionally generic and additive. It does not require changing
        the existing stage contracts. It extracts commonly useful metrics if they exist.
        """
        metrics: dict[str, Any] = {}

        metrics_model = getattr(output_model, "metrics", None)
        if metrics_model is not None:
            if hasattr(metrics_model, "model_dump"):
                metrics.update(metrics_model.model_dump(mode="json"))
            elif hasattr(metrics_model, "__dict__"):
                metrics.update(metrics_model.__dict__)

        # Add a few derived counts where useful.
        for field_name in ("sections", "chunks", "indexed_documents", "decisions", "extraction_records", "handled_candidates"):
            field_value = getattr(output_model, field_name, None)
            if isinstance(field_value, list):
                metrics[f"{field_name}_count"] = len(field_value)

        return metrics

    def _estimate_stage_cost(
        self,
        *,
        context: IngestionRunContext,
        stage_name: str,
        usage_metrics: dict[str, Any],
    ) -> dict[str, Any]:
        if self._cost_estimator_service is None:
            return {}

        estimates: list[dict[str, Any]] = []
        try:
            if stage_name == "stage_2_runner":
                page_count = usage_metrics.get("page_count")
                units = float(page_count) if isinstance(page_count, (int, float)) and page_count > 0 else 1.0
                estimate = self._cost_estimator_service.estimate_service_cost(
                    service_name="azure_document_intelligence",
                    units=units,
                    category="ingestion_document_intelligence",
                    metadata={"stage_name": stage_name, "run_id": context.run_id},
                )
                estimates.append(estimate.model_dump())
            elif stage_name in {"stage_1_runner", "stage_3_runner", "stage_4_runner", "stage_5_runner"}:
                estimate = self._cost_estimator_service.estimate_service_cost(
                    service_name="azure_blob_storage",
                    units=1.0,
                    category="ingestion_blob_storage",
                    metadata={"stage_name": stage_name, "run_id": context.run_id},
                )
                estimates.append(estimate.model_dump())
            elif stage_name == "stage_9_runner":
                indexed_count = usage_metrics.get("indexed_documents_count")
                search_units = float(indexed_count) if isinstance(indexed_count, (int, float)) and indexed_count > 0 else 1.0
                search_estimate = self._cost_estimator_service.estimate_service_cost(
                    service_name="azure_search",
                    units=search_units,
                    category="ingestion_search_indexing",
                    metadata={"stage_name": stage_name, "run_id": context.run_id},
                )
                blob_estimate = self._cost_estimator_service.estimate_service_cost(
                    service_name="azure_blob_storage",
                    units=1.0,
                    category="ingestion_blob_storage",
                    metadata={"stage_name": stage_name, "run_id": context.run_id},
                )
                estimates.extend([search_estimate.model_dump(), blob_estimate.model_dump()])
        except Exception:
            return {}

        total_amount = 0.0
        currency = "USD"
        for estimate_dict in estimates:
            amount = estimate_dict.get("amount")
            if isinstance(amount, (int, float)):
                total_amount += float(amount)
            if isinstance(estimate_dict.get("currency"), str):
                currency = estimate_dict["currency"]

        if self._cost_aggregation_service is not None:
            for estimate_dict in estimates:
                try:
                    from backend.modules.observability.services.cost_estimator_service import CostEstimate
                    estimate = CostEstimate(**estimate_dict)
                    self._cost_aggregation_service.add_cost_record(
                        job_id=context.run_id,
                        category=str(estimate.category),
                        estimate=estimate,
                        metadata={"stage_name": stage_name},
                    )
                except Exception:
                    continue

        return {
            "amount": round(total_amount, 10),
            "currency": currency,
            "line_items": estimates,
        }