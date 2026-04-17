from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.application.services.document_service import DocumentService
from backend.core.config import get_settings
from backend.modules.ingestion.contracts.stage_1_contracts import Stage1Input
from backend.pipeline.bootstrap.ingestion_bootstrap import (
    build_ingestion_stage_runners,
    build_observed_orchestrator,
)
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
from backend.modules.observability.services.cost_aggregation_service import (
    CostAggregationService,
)
from backend.modules.observability.services.cost_estimator_service import (
    CostEstimatorService,
)
from backend.modules.observability.services.pricing_registry_service import (
    PricingRegistryService,
)
from backend.pipeline.orchestrators.ingestion_orchestrator import IngestionRunConfig


@dataclass
class IngestionRuntime:
    """
    Fully wired ingestion runtime.
    """

    repository: Any
    stage_runners: dict[str, Any]
    logs_root: Path

    async def run_ingestion(
        self,
        *,
        workflow_run_id: str,
        document_id: str,
        ingestion_execution_id: str,
    ) -> Any:
        # Keep signature aligned with workflow bridge contract.
        _ = ingestion_execution_id

        doc_service = DocumentService()
        doc = doc_service.get_document(document_id)
        file_bytes = doc_service.get_document_bytes(document_id)

        stage_1_input = Stage1Input(
            file_name=doc.filename,
            content_type=doc.content_type,
            file_bytes=file_bytes,
            correlation_id=workflow_run_id,
        )

        run_config = IngestionRunConfig()
        run_paths = RunPaths(
            root_dir=self.logs_root / workflow_run_id,
            logs_dir=self.logs_root / workflow_run_id / "logs",
            artifacts_dir=self.logs_root / workflow_run_id / "artifacts",
            official_log_path=self.logs_root / workflow_run_id / "logs" / "official.log",
            demo_log_path=self.logs_root / workflow_run_id / "logs" / "demo.log",
        )
        context = IngestionRunContext(
            run_id=workflow_run_id,
            started_at=datetime.now(UTC),
            file_name=doc.filename,
            content_type=doc.content_type,
            file_size_bytes=len(file_bytes),
            log_mode=LogMode.BOTH,
            paths=run_paths,
        )
        cost_aggregation_service = CostAggregationService()
        observer = FileIngestionObserver(
            logger=LoggerMultiplexer(
                official_logger=OfficialFileLogger(log_path=run_paths.official_log_path),
                demo_logger=DemoFileLogger(log_path=run_paths.demo_log_path),
            ),
            artifact_store=LocalArtifactStore(artifacts_root=run_paths.artifacts_dir),
            cost_estimator_service=CostEstimatorService(
                pricing_registry_service=PricingRegistryService()
            ),
            cost_aggregation_service=cost_aggregation_service,
        )
        observer.on_run_started(context=context)

        orchestrator = build_observed_orchestrator(
            stage_runners=self.stage_runners,
            observer=observer,
            context=context,
        )
        try:
            if hasattr(orchestrator, "run"):
                result = await orchestrator.run(
                    stage_1_input=stage_1_input,
                    config=run_config,
                )
            elif hasattr(orchestrator, "execute"):
                result = await orchestrator.execute(
                    stage_1_input=stage_1_input,
                    config=run_config,
                )
            else:
                raise RuntimeError("Ingestion orchestrator must expose 'run' or 'execute'.")
            observer.on_run_completed(
                context=context,
                final_status=str(getattr(result, "status", "COMPLETED")),
                stage_count=9,
            )
            try:
                cost_summary = cost_aggregation_service.get_summary(context.run_id).model_dump()
            except Exception:
                cost_summary = {}
            return {
                "status": str(getattr(result, "status", "COMPLETED")),
                "current_stage": str(getattr(result, "current_stage", "COMPLETED")),
                "completed_stages": int(getattr(result, "completed_stages", 9)),
                "total_stages": int(getattr(result, "total_stages", 9)),
                "warnings": list(getattr(result, "warnings", [])),
                "errors": list(getattr(result, "errors", [])),
                "artifacts": list(getattr(result, "artifacts", [])),
                "cost_summary": cost_summary,
                "workflow_run_id": workflow_run_id,
                "document_id": document_id,
                "stage": "ingestion",
            }
        except Exception as exc:
            observer.on_run_failed(context=context, error_message=str(exc))
            raise



def build_ingestion_runtime(*, repo_dir: Path | None = None) -> IngestionRuntime:
    """
    Build the live ingestion runtime using environment-based configuration.
    """
    if repo_dir is None:
        settings = get_settings()
        repo_dir = settings.executions_path / "ingestion"

    repository, stage_runners = build_ingestion_stage_runners(repo_dir=repo_dir)
    return IngestionRuntime(
        repository=repository,
        stage_runners=stage_runners,
        logs_root=settings.logs_path / "ingestion_runs",
    )
