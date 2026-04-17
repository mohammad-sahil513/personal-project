"""
Generation orchestrator for the Generation module.

Responsibilities:
- Execute one Generation job over a prepared set of section plans
- Delegate dependency-aware execution to WaveExecutor
- Aggregate section outcomes into a job-level summary/status
- Publish final SSE lifecycle events
- Optionally invoke a job snapshot hook
- Emit shared observability logs and job-level cost summary

Important:
- This file is job orchestration only.
- It does NOT do final assembly/TOC/export yet.
- It assumes section planning has already happened upstream.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.generation.contracts.generation_contracts import (
    GenerationJobResponse,
    GenerationJobStatus,
    GenerationJobSummary,
    SectionExecutionStatus,
)
from backend.modules.generation.orchestrators.wave_executor import (
    WaveExecutionResponse,
    WaveExecutor,
    WaveSectionPlan,
)
from backend.modules.generation.streaming.sse_publisher import (
    SSEEventType,
    SSEPublisher,
)
from backend.modules.observability.services.cost_aggregation_service import (
    CostAggregationService,
)
from backend.modules.observability.services.logging_service import (
    LoggingService,
)
from backend.modules.observability.services.request_context_service import (
    RequestContextService,
)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


@runtime_checkable
class JobSnapshotWriter(Protocol):
    """
    Optional snapshot hook invoked after job completion/failure.
    """

    def snapshot_job_result(
        self,
        *,
        job_response: GenerationJobResponse,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Persist a job-level snapshot and return snapshot metadata.
        """
        ...


class GenerationOrchestratorRequest(BaseModel):
    """
    Input payload for one top-level Generation job orchestration run.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(description="Stable Generation job identifier.")
    document_id: str = Field(description="Target source/document identifier.")
    template_id: str = Field(description="Template identifier used for the job.")
    template_version: str | None = Field(default=None)
    plans: list[WaveSectionPlan] = Field(
        default_factory=list,
        description="Prepared section execution plans for the job.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional orchestration metadata.",
    )


class GenerationOrchestratorResponse(BaseModel):
    """
    Final response from the Generation job orchestrator.
    """

    model_config = ConfigDict(extra="forbid")

    job_response: GenerationJobResponse = Field(
        description="Aggregated job-level Generation response."
    )
    wave_execution: WaveExecutionResponse = Field(
        description="Wave execution details used during the job."
    )
    snapshot_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional snapshot metadata from the job snapshot hook.",
    )
    cost_metadata: dict[str, Any] | None = Field(
        default=None,
        description="Optional cost summary metadata for observability.",
    )


class GenerationOrchestrator:
    """
    Top-level Generation job orchestrator.

    Flow:
    - set shared correlation context
    - log job start
    - delegate execution to WaveExecutor
    - aggregate section results
    - derive final job status
    - publish generation_completed or generation_failed
    - optionally snapshot the final job response
    - optionally log and return job-level cost summary
    """

    def __init__(
        self,
        *,
        wave_executor: WaveExecutor,
        sse_publisher: SSEPublisher,
        logging_service: LoggingService | None = None,
        request_context_service: RequestContextService | None = None,
        cost_aggregation_service: CostAggregationService | None = None,
        job_snapshot_writer: JobSnapshotWriter | None = None,
    ) -> None:
        self.wave_executor = wave_executor
        self.sse_publisher = sse_publisher
        self.request_context_service = request_context_service or RequestContextService()
        self.logging_service = logging_service or LoggingService(
            context_provider=self.request_context_service.get_context_dict
        )
        self.cost_aggregation_service = cost_aggregation_service
        self.job_snapshot_writer = job_snapshot_writer

    def run(self, request: GenerationOrchestratorRequest) -> GenerationOrchestratorResponse:
        """
        Execute one Generation job from section plans to job-level result.
        """
        created_at = utc_now()

        # Shared observability correlation context
        self.request_context_service.start_job_context(
            job_id=request.job_id,
            document_id=request.document_id,
            template_id=request.template_id,
            template_version=request.template_version,
        )

        try:
            self.logging_service.info(
                "generation_job_started",
                job_id=request.job_id,
                document_id=request.document_id,
                template_id=request.template_id,
                template_version=request.template_version,
                planned_section_count=len(request.plans),
            )

            wave_execution = self.wave_executor.execute(request.plans)

            self.logging_service.info(
                "generation_wave_execution_completed",
                job_id=request.job_id,
                document_id=request.document_id,
                wave_count=len(wave_execution.wave_summaries),
                executed_section_count=len(wave_execution.section_responses),
            )

            summary = self._build_summary(wave_execution)
            final_status = self._derive_job_status(summary)

            job_response = GenerationJobResponse(
                job_id=request.job_id,
                document_id=request.document_id,
                template_id=request.template_id,
                template_version=request.template_version,
                status=final_status,
                summary=summary,
                section_results=[resp.result for resp in wave_execution.section_responses],
                export_summary=None,  # Phase 5/6+ will fill this later in runtime integration
                created_at=created_at,
                updated_at=utc_now(),
            )

            if final_status == GenerationJobStatus.FAILED:
                self.logging_service.error(
                    "generation_job_failed",
                    job_id=request.job_id,
                    document_id=request.document_id,
                    template_id=request.template_id,
                    failed_sections=summary.failed_sections,
                    total_sections=summary.total_sections,
                )

                self.sse_publisher.publish(
                    job_id=request.job_id,
                    event=SSEEventType.GENERATION_FAILED,
                    outcome=final_status.value,
                    data={
                        "document_id": request.document_id,
                        "template_id": request.template_id,
                        "failed_sections": summary.failed_sections,
                    },
                )
            else:
                self.logging_service.info(
                    "generation_job_completed",
                    job_id=request.job_id,
                    document_id=request.document_id,
                    template_id=request.template_id,
                    status=final_status.value,
                    generated_sections=summary.generated_sections,
                    degraded_sections=summary.degraded_sections,
                    skipped_sections=summary.skipped_sections,
                    failed_sections=summary.failed_sections,
                )

                self.sse_publisher.publish(
                    job_id=request.job_id,
                    event=SSEEventType.GENERATION_COMPLETED,
                    outcome=final_status.value,
                    data={
                        "document_id": request.document_id,
                        "template_id": request.template_id,
                        "generated_sections": summary.generated_sections,
                        "degraded_sections": summary.degraded_sections,
                        "failed_sections": summary.failed_sections,
                        "skipped_sections": summary.skipped_sections,
                    },
                )

            snapshot_metadata = self._snapshot_if_configured(
                job_response=job_response,
                metadata=request.metadata,
            )

            cost_metadata = self._build_cost_summary(request.job_id)

            return GenerationOrchestratorResponse(
                job_response=job_response,
                wave_execution=wave_execution,
                snapshot_metadata=snapshot_metadata,
                cost_metadata=cost_metadata,
            )
        finally:
            self.request_context_service.clear_context()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_summary(self, wave_execution: WaveExecutionResponse) -> GenerationJobSummary:
        """
        Aggregate section-level results into a job-level summary.
        """
        total = len(wave_execution.section_responses)
        pending = 0
        running = 0
        generated = 0
        degraded = 0
        skipped = 0
        failed = 0

        for response in wave_execution.section_responses:
            status = response.result.status

            if status == SectionExecutionStatus.PENDING:
                pending += 1
            elif status == SectionExecutionStatus.RUNNING:
                running += 1
            elif status == SectionExecutionStatus.GENERATED:
                generated += 1
            elif status == SectionExecutionStatus.DEGRADED:
                degraded += 1
            elif status == SectionExecutionStatus.SKIPPED:
                skipped += 1
            elif status == SectionExecutionStatus.FAILED:
                failed += 1

        return GenerationJobSummary(
            total_sections=total,
            pending_sections=pending,
            running_sections=running,
            generated_sections=generated,
            degraded_sections=degraded,
            skipped_sections=skipped,
            failed_sections=failed,
        )

    def _derive_job_status(self, summary: GenerationJobSummary) -> GenerationJobStatus:
        """
        Derive the final job-level status from the section summary.

        Rules:
        - all sections failed -> FAILED
        - any failed or any skipped -> PARTIAL
        - otherwise -> COMPLETED
        """
        if summary.total_sections == 0:
            return GenerationJobStatus.FAILED

        if summary.failed_sections == summary.total_sections:
            return GenerationJobStatus.FAILED

        if summary.failed_sections > 0 or summary.skipped_sections > 0:
            return GenerationJobStatus.PARTIAL

        return GenerationJobStatus.COMPLETED

    def _snapshot_if_configured(
        self,
        *,
        job_response: GenerationJobResponse,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """
        Invoke the job snapshot hook when configured.
        """
        if self.job_snapshot_writer is None:
            return None

        return self.job_snapshot_writer.snapshot_job_result(
            job_response=job_response,
            metadata=metadata or {},
        )

    def _build_cost_summary(self, job_id: str) -> dict[str, Any] | None:
        """
        Best-effort job-level cost summary.

        Cost observability must never break orchestration.
        """
        if self.cost_aggregation_service is None:
            return None

        try:
            summary = self.cost_aggregation_service.get_summary(job_id)

            self.logging_service.info(
                "generation_job_cost_summary",
                job_id=job_id,
                total_amount=summary.total_amount,
                currency=summary.currency,
                record_count=summary.record_count,
                by_category=summary.by_category,
                by_section=summary.by_section,
            )

            return summary.model_dump()
        except Exception as exc:
            self.logging_service.warning(
                "generation_job_cost_summary_failed",
                job_id=job_id,
                error_message=str(exc),
            )
            return {
                "error": str(exc),
            }
