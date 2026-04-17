"""
Workflow execution shell service.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import BackgroundTasks

from backend.application.services.document_assembly_service import DocumentAssemblyService
from backend.application.services.ingestion_integration_service import (
    IngestionIntegrationService,
)
from backend.application.services.ingestion_runtime_bridge import IngestionRuntimeBridge
from backend.application.services.output_export_service import OutputExportService
from backend.application.services.progress_service import ProgressService
from backend.application.services.section_planning_service import SectionPlanningService
from backend.application.services.section_progress_service import SectionProgressService
from backend.application.services.workflow_event_service import (
    WorkflowEventService,
    get_workflow_event_service,
)
from backend.application.services.workflow_section_generation_service import (
    WorkflowSectionGenerationService,
)
from backend.application.services.workflow_service import WorkflowService
from backend.core.exceptions import BackendError, ValidationError
from backend.core.logging import get_logger
from backend.workers.task_dispatcher import TaskDispatcher

logger = get_logger(__name__)


class WorkflowExecutorService:
    """
    Workflow execution shell with ingestion child-execution linkage, real
    ingestion runtime bridge support, section planning/progress integration,
    generation integration, assembly foundation hooks, output export
    preparation/rendering hooks, workflow SSE event publishing, and
    hardening/error propagation.
    """

    def __init__(
        self,
        workflow_service: WorkflowService | None = None,
        progress_service: ProgressService | None = None,
        task_dispatcher: TaskDispatcher | None = None,
        ingestion_integration_service: IngestionIntegrationService | None = None,
        ingestion_runtime_bridge: IngestionRuntimeBridge | None = None,
        section_planning_service: SectionPlanningService | None = None,
        section_progress_service: SectionProgressService | None = None,
        workflow_section_generation_service: WorkflowSectionGenerationService | None = None,
        document_assembly_service: DocumentAssemblyService | None = None,
        output_export_service: OutputExportService | None = None,
        workflow_event_service: WorkflowEventService | None = None,
    ) -> None:
        self.workflow_service = workflow_service or WorkflowService()
        self.progress_service = progress_service or ProgressService()
        self.task_dispatcher = task_dispatcher or TaskDispatcher()
        self.ingestion_integration_service = (
            ingestion_integration_service or IngestionIntegrationService()
        )

        self.ingestion_runtime_bridge = ingestion_runtime_bridge or IngestionRuntimeBridge()
        self.section_planning_service = section_planning_service or SectionPlanningService()
        self.section_progress_service = section_progress_service or SectionProgressService()
        self.workflow_section_generation_service = (
            workflow_section_generation_service or WorkflowSectionGenerationService()
        )
        self.document_assembly_service = document_assembly_service or DocumentAssemblyService()
        self.output_export_service = output_export_service or OutputExportService()
        self.workflow_event_service = workflow_event_service or get_workflow_event_service()

    async def handle_workflow_failure(
        self,
        workflow_run_id: str,
        exc: Exception,
        *,
        phase: str | None = None,
        section_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Mark the workflow as failed and publish a workflow.failed event.
        """
        if isinstance(exc, BackendError):
            error_code = exc.error_code
            error_message = exc.message
        else:
            error_code = "WORKFLOW_RUNTIME_ERROR"
            error_message = str(exc) or exc.__class__.__name__

        failed = self.workflow_service.mark_workflow_failed(
            workflow_run_id,
            error_code=error_code,
            error_message=error_message,
        )

        payload = {
            "error_code": error_code,
            "message": error_message,
        }
        if section_id is not None:
            payload["section_id"] = section_id

        await self.workflow_event_service.publish(
            workflow_run_id=workflow_run_id,
            event_type="workflow.failed",
            phase=phase or failed.current_phase,
            payload=payload,
        )

        logger.error(
            "Workflow marked failed",
            extra={
                "workflow_run_id": workflow_run_id,
                "phase": phase or failed.current_phase,
                "section_id": section_id,
                "error_code": error_code,
                "error_message": error_message,
            },
        )

        return failed.to_dict()

    def _to_iso(self, value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value
        if isinstance(value, datetime):
            return value.isoformat()
        return str(value)

    def _duration_ms(self, started_at: Any, completed_at: Any) -> int | None:
        if not started_at or not completed_at:
            return None
        try:
            start = started_at if isinstance(started_at, datetime) else datetime.fromisoformat(str(started_at))
            end = completed_at if isinstance(completed_at, datetime) else datetime.fromisoformat(str(completed_at))
            return max(0, int((end - start).total_seconds() * 1000))
        except Exception:
            return None

    def _build_observability_summary(self, workflow: Any) -> dict[str, Any]:
        stage_statuses: dict[str, dict[str, Any]] = {}
        for phase in (workflow.phases or []):
            phase_name = str(phase.get("phase", "")).lower()
            stage_statuses[phase_name] = {
                "status": phase.get("status"),
                "progress_percent": phase.get("progress_percent"),
                "started_at": self._to_iso(phase.get("started_at")),
                "completed_at": self._to_iso(phase.get("completed_at")),
                "duration_ms": self._duration_ms(phase.get("started_at"), phase.get("completed_at")),
            }

        generation_total = 0.0
        per_section_generation: dict[str, float] = {}
        for section_id, section_result in (workflow.section_generation_results or {}).items():
            diagnostics = section_result.get("diagnostics", {})
            cost_metadata = diagnostics.get("cost_metadata", {}) if isinstance(diagnostics, dict) else {}
            estimate = cost_metadata.get("estimate", {}) if isinstance(cost_metadata, dict) else {}
            amount = estimate.get("amount") if isinstance(estimate, dict) else None
            if isinstance(amount, (int, float)):
                value = float(amount)
                generation_total += value
                per_section_generation[str(section_id)] = value

        retrieval_total = 0.0
        per_section_retrieval: dict[str, float] = {}
        for section_id, retrieval_result in (workflow.section_retrieval_results or {}).items():
            if not isinstance(retrieval_result, dict):
                continue
            diagnostics = retrieval_result.get("diagnostics", {})
            cost_summary = diagnostics.get("cost_summary", {}) if isinstance(diagnostics, dict) else {}
            amount = cost_summary.get("total_amount") if isinstance(cost_summary, dict) else None
            if isinstance(amount, (int, float)):
                value = float(amount)
                retrieval_total += value
                per_section_retrieval[str(section_id)] = value

        existing = workflow.observability_summary or {}
        existing_costs = existing.get("cost_totals", {}) if isinstance(existing, dict) else {}
        ingestion_total = existing_costs.get("ingestion", 0.0)
        if not isinstance(ingestion_total, (int, float)):
            ingestion_total = 0.0

        total_cost = float(ingestion_total) + retrieval_total + generation_total
        return {
            "workflow_run_id": workflow.workflow_run_id,
            "document_id": workflow.document_id,
            "template_id": workflow.template_id,
            "status": workflow.status,
            "current_phase": workflow.current_phase,
            "stage_statuses": stage_statuses,
            "cost_totals": {
                "ingestion": round(float(ingestion_total), 10),
                "retrieval": round(retrieval_total, 10),
                "generation": round(generation_total, 10),
                "assembly": 0.0,
                "export": 0.0,
                "document_total": round(total_cost, 10),
            },
            "per_section_totals": {
                "retrieval": per_section_retrieval,
                "generation": per_section_generation,
            },
            "updated_at": self._to_iso(workflow.updated_at),
        }

    def _refresh_observability_summary(self, workflow_run_id: str) -> None:
        latest = self.workflow_service.get_workflow(workflow_run_id)
        self.workflow_service.update_workflow(
            workflow_run_id,
            {"observability_summary": self._build_observability_summary(latest)},
        )

    def prepare_workflow_execution(self, workflow_run_id: str) -> dict[str, Any]:
        """
        Initialize workflow progress state before execution starts.
        """
        progress_snapshot = self.progress_service.initialize_progress()

        updated = self.workflow_service.update_workflow(
            workflow_run_id,
            {
                "current_phase": progress_snapshot["current_phase"],
                "overall_progress_percent": progress_snapshot["overall_progress_percent"],
                "phases": progress_snapshot["phases"],
            },
        )

        logger.info(
            "Workflow execution prepared",
            extra={"workflow_run_id": workflow_run_id},
        )

        return updated.to_dict()

    async def build_and_attach_section_plan(self, workflow_run_id: str) -> dict[str, Any]:
        workflow = self.workflow_service.get_workflow(workflow_run_id)

        if not workflow.template_id:
            raise ValidationError(
                message="Workflow template_id is required for section planning",
                error_code="SECTION_PLAN_TEMPLATE_REQUIRED",
                details={"workflow_run_id": workflow_run_id},
            )

        section_plan = await self.section_planning_service.build_plan_dict(workflow.template_id)

        updated = self.workflow_service.attach_section_plan(
            workflow_run_id,
            section_plan=section_plan,
        )

        await self.workflow_event_service.publish(
            workflow_run_id=workflow_run_id,
            event_type="section.plan.attached",
            phase="SECTION_PLANNING",
            payload={
                "template_id": workflow.template_id,
                "total_sections": section_plan.get("total_sections"),
            },
        )

        logger.info(
            "Section plan attached to workflow",
            extra={
                "workflow_run_id": workflow_run_id,
                "template_id": workflow.template_id,
                "total_sections": section_plan.get("total_sections"),
            },
        )
        self._refresh_observability_summary(workflow_run_id)

        return updated.to_dict()

    async def initialize_section_progress(self, workflow_run_id: str) -> dict[str, Any]:
        workflow = self.workflow_service.get_workflow(workflow_run_id)

        if not workflow.section_plan:
            raise ValidationError(
                message="Workflow section_plan is required to initialize section progress",
                error_code="SECTION_PROGRESS_PLAN_REQUIRED",
                details={"workflow_run_id": workflow_run_id},
            )

        section_progress = self.section_progress_service.initialize_from_section_plan(
            workflow.section_plan
        ).to_dict()

        updated = self.workflow_service.attach_section_progress(
            workflow_run_id,
            section_progress=section_progress,
        )

        await self.workflow_event_service.publish(
            workflow_run_id=workflow_run_id,
            event_type="section.progress.initialized",
            phase="SECTION_PLANNING",
            payload={
                "total_sections": section_progress.get("total_sections"),
                "completed_sections": section_progress.get("completed_sections"),
                "running_sections": section_progress.get("running_sections"),
                "failed_sections": section_progress.get("failed_sections"),
            },
        )

        logger.info(
            "Section progress initialized for workflow",
            extra={
                "workflow_run_id": workflow_run_id,
                "total_sections": section_progress.get("total_sections"),
            },
        )
        self._refresh_observability_summary(workflow_run_id)

        return updated.to_dict()

    async def run_section_generation(self, workflow_run_id: str) -> dict[str, Any]:
        workflow = self.workflow_service.get_workflow(workflow_run_id)

        if not workflow.section_plan:
            raise ValidationError(
                message="Workflow section_plan is required for generation",
                error_code="WORKFLOW_GENERATION_PLAN_REQUIRED",
                details={"workflow_run_id": workflow_run_id},
            )

        if not workflow.section_retrieval_results:
            raise ValidationError(
                message="Workflow section_retrieval_results are required for generation",
                error_code="WORKFLOW_GENERATION_RETRIEVAL_REQUIRED",
                details={"workflow_run_id": workflow_run_id},
            )

        if not workflow.section_progress:
            raise ValidationError(
                message="Workflow section_progress must be initialized before generation",
                error_code="WORKFLOW_GENERATION_PROGRESS_REQUIRED",
                details={"workflow_run_id": workflow_run_id},
            )

        section_progress = workflow.section_progress
        generation_results: dict[str, Any] = {}

        for section in workflow.section_plan["sections"]:
            section_id = section["section_id"]

            # 1) Mark section RUNNING
            section_progress = self.section_progress_service.mark_section_running(
                section_progress,
                section_id,
            ).to_dict()

            self.workflow_service.attach_section_progress(
                workflow_run_id,
                section_progress=section_progress,
            )

            await self.workflow_event_service.publish(
                workflow_run_id=workflow_run_id,
                event_type="section.generation.started",
                phase="GENERATION",
                payload={
                    "workflow_run_id": workflow_run_id,
                    "document_id": workflow.document_id,
                    "template_id": workflow.template_id,
                    "section_id": section_id,
                    "title": section.get("title"),
                    "generation_strategy": section.get("generation_strategy"),
                    "stage": "generation",
                    "status": "STARTED",
                },
            )

            try:
                # 2) Run generation for this single section
                generation_result = await self.workflow_section_generation_service.run_generation_for_workflow(
                    section_plan={
                        "sections": [section],
                    },
                    section_retrieval_results={
                        section_id: workflow.section_retrieval_results[section_id],
                    },
                    workflow_run_id=workflow_run_id,
                    document_id=workflow.document_id,
                    template_id=workflow.template_id,
                    template_version=None,
                )

                generation_results[section_id] = generation_result[section_id]

                # 3) Mark section COMPLETED
                section_progress = self.section_progress_service.mark_section_completed(
                    section_progress,
                    section_id,
                ).to_dict()

                await self.workflow_event_service.publish(
                    workflow_run_id=workflow_run_id,
                    event_type="section.generation.completed",
                    phase="GENERATION",
                    payload={
                        "workflow_run_id": workflow_run_id,
                        "document_id": workflow.document_id,
                        "template_id": workflow.template_id,
                        "section_id": section_id,
                        "title": section.get("title"),
                        "output_type": generation_results[section_id]["output_type"],
                        "stage": "generation",
                        "status": "COMPLETED",
                    },
                )

            except Exception as exc:
                # 4) Mark section FAILED
                section_progress = self.section_progress_service.mark_section_failed(
                    section_progress,
                    section_id,
                ).to_dict()

                self.workflow_service.attach_section_progress(
                    workflow_run_id,
                    section_progress=section_progress,
                )

                await self.workflow_event_service.publish(
                    workflow_run_id=workflow_run_id,
                    event_type="section.generation.failed",
                    phase="GENERATION",
                    payload={
                        "workflow_run_id": workflow_run_id,
                        "document_id": workflow.document_id,
                        "template_id": workflow.template_id,
                        "section_id": section_id,
                        "title": section.get("title"),
                        "error": str(exc),
                        "stage": "generation",
                        "status": "FAILED",
                    },
                )

                await self.handle_workflow_failure(
                    workflow_run_id,
                    exc,
                    phase="GENERATION",
                    section_id=section_id,
                )

                raise

            # 5) Update workflow progress from section progress
            overall_progress = self.section_progress_service.calculate_overall_progress_percent(
                section_progress
            )

            self.workflow_service.attach_section_progress(
                workflow_run_id,
                section_progress=section_progress,
            )

            self.workflow_service.update_progress_from_sections(
                workflow_run_id,
                overall_progress_percent=overall_progress,
            )

        # 6) Persist generation results after all sections
        updated = self.workflow_service.attach_section_generation_results(
            workflow_run_id,
            section_generation_results=generation_results,
        )

        total_estimated_cost = 0.0
        for section_result in generation_results.values():
            diagnostics = section_result.get("diagnostics", {})
            cost_metadata = diagnostics.get("cost_metadata", {})
            if not isinstance(cost_metadata, dict):
                continue
            estimate = cost_metadata.get("estimate", {})
            if isinstance(estimate, dict):
                amount = estimate.get("amount")
                if isinstance(amount, (int, float)):
                    total_estimated_cost += float(amount)
        logger.info(
            "Workflow generation phase summary",
            extra={
                "workflow_run_id": workflow_run_id,
                "generated_sections": len(generation_results),
                "estimated_generation_cost_total": round(total_estimated_cost, 10),
                "phase": "GENERATION",
            },
        )
        self._refresh_observability_summary(workflow_run_id)

        return updated.to_dict()

    async def assemble_generated_sections(self, workflow_run_id: str) -> dict[str, Any]:
        try:
            workflow = self.workflow_service.get_workflow(workflow_run_id)

            if not workflow.section_plan:
                raise ValidationError(
                    message="Workflow section_plan is required for assembly",
                    error_code="WORKFLOW_ASSEMBLY_PLAN_REQUIRED",
                    details={"workflow_run_id": workflow_run_id},
                )

            if not workflow.section_generation_results:
                raise ValidationError(
                    message="Workflow section_generation_results are required for assembly",
                    error_code="WORKFLOW_ASSEMBLY_GENERATION_REQUIRED",
                    details={"workflow_run_id": workflow_run_id},
                )

            assembled_document = self.document_assembly_service.build_assembled_document(
                workflow_run_id=workflow.workflow_run_id,
                template_id=workflow.template_id,
                section_plan=workflow.section_plan,
                section_generation_results=workflow.section_generation_results,
            ).to_dict()

            updated = self.workflow_service.attach_assembled_document(
                workflow_run_id,
                assembled_document=assembled_document,
            )

            await self.workflow_event_service.publish(
                workflow_run_id=workflow_run_id,
                event_type="workflow.assembled",
                phase="ASSEMBLY",
                payload={
                    "workflow_run_id": workflow_run_id,
                    "document_id": workflow.document_id,
                    "template_id": workflow.template_id,
                    "total_sections": assembled_document.get("total_sections"),
                    "title": assembled_document.get("title"),
                    "stage": "assembly",
                    "status": "COMPLETED",
                },
            )

            logger.info(
                "Assembled document attached to workflow",
                extra={
                    "workflow_run_id": workflow_run_id,
                    "total_sections": assembled_document.get("total_sections"),
                },
            )
            self._refresh_observability_summary(workflow_run_id)

            return updated.to_dict()

        except Exception as exc:
            await self.handle_workflow_failure(
                workflow_run_id,
                exc,
                phase="ASSEMBLY",
            )
            raise

    async def prepare_output_export(self, workflow_run_id: str) -> dict[str, Any]:
        workflow = self.workflow_service.get_workflow(workflow_run_id)

        if not workflow.assembled_document:
            raise ValidationError(
                message="assembled_document is required for export preparation",
                error_code="EXPORT_ASSEMBLY_REQUIRED",
                details={"workflow_run_id": workflow_run_id},
            )

        output = self.output_export_service.prepare_docx_export(
            workflow_run_id=workflow_run_id,
            assembled_document=workflow.assembled_document,
        )

        updated = self.workflow_service.attach_output(
            workflow_run_id,
            output_id=output["output_id"],
        )
        self._refresh_observability_summary(workflow_run_id)

        return updated.to_dict()

    async def render_and_finalize_output(self, workflow_run_id: str) -> dict[str, Any]:
        try:
            workflow = self.workflow_service.get_workflow(workflow_run_id)

            if not workflow.output_id:
                raise ValidationError(
                    message="workflow.output_id is required to render output",
                    error_code="OUTPUT_RENDER_INVALID",
                    details={"workflow_run_id": workflow_run_id},
                )

            if not workflow.assembled_document:
                raise ValidationError(
                    message="assembled_document is required to render output",
                    error_code="OUTPUT_RENDER_INVALID",
                    details={"workflow_run_id": workflow_run_id},
                )

            output = self.output_export_service.export_docx(
                output_id=workflow.output_id,
                workflow_run_id=workflow_run_id,
                assembled_document=workflow.assembled_document,
            )

            await self.workflow_event_service.publish(
                workflow_run_id=workflow_run_id,
                event_type="output.ready",
                phase="EXPORT",
                payload={
                    "workflow_run_id": workflow_run_id,
                    "document_id": workflow.document_id,
                    "template_id": workflow.template_id,
                    "output_id": output["output_id"],
                    "format": output["format"],
                    "status": output["status"],
                    "stage": "export",
                },
            )
            self._refresh_observability_summary(workflow_run_id)

            return output

        except Exception as exc:
            await self.handle_workflow_failure(
                workflow_run_id,
                exc,
                phase="EXPORT",
            )
            raise

    async def execute_workflow_skeleton(self, workflow_run_id: str) -> dict[str, Any]:
        """
        Minimal workflow execution shell with ingestion bridge integration and
        workflow.started SSE event publishing.
        """
        workflow = self.workflow_service.get_workflow(workflow_run_id)

        if not workflow.phases:
            self.prepare_workflow_execution(workflow_run_id)
            workflow = self.workflow_service.get_workflow(workflow_run_id)

        started = self.workflow_service.mark_workflow_started(workflow_run_id)

        await self.workflow_event_service.publish(
            workflow_run_id=workflow_run_id,
            event_type="workflow.started",
            phase="INPUT_PREPARATION",
            payload={
                "workflow_run_id": workflow_run_id,
                "document_id": started.document_id,
                "template_id": started.template_id,
                "stage": "input_preparation",
                "status": "STARTED",
            },
        )

        ingestion_exec = self.ingestion_integration_service.find_ingestion_execution_for_workflow(
            workflow_run_id
        )

        if ingestion_exec is None:
            ingestion_exec = self.ingestion_integration_service.create_ingestion_execution(
                workflow_run_id=workflow_run_id,
                document_id=started.document_id,
            )

        current_workflow = self.workflow_service.get_workflow(workflow_run_id)
        current_refs = dict(current_workflow.execution_refs or {})

        if current_refs.get("INGESTION") != ingestion_exec.execution_id:
            self.workflow_service.attach_execution_ref(
                workflow_run_id,
                execution_type="INGESTION",
                execution_id=ingestion_exec.execution_id,
            )

        progress_snapshot = self.progress_service.mark_phase_completed(
            started.phases or [],
            "INPUT_PREPARATION",
        )

        self.workflow_service.update_workflow(
            workflow_run_id,
            {
                "current_phase": progress_snapshot["current_phase"],
                "overall_progress_percent": progress_snapshot["overall_progress_percent"],
                "phases": progress_snapshot["phases"],
            },
        )

        self.ingestion_integration_service.mark_ingestion_running(
            ingestion_exec.execution_id,
            current_stage="01_UPLOAD_AND_DEDUP",
        )

        bridge_result = await self.ingestion_runtime_bridge.run_ingestion(
            workflow_run_id=workflow_run_id,
            document_id=started.document_id,
            ingestion_execution_id=ingestion_exec.execution_id,
        )

        final_workflow = self._apply_ingestion_bridge_result(
            workflow_run_id=workflow_run_id,
            ingestion_execution_id=ingestion_exec.execution_id,
            bridge_result=bridge_result,
        )

        logger.info(
            "Workflow execution applied real ingestion result",
            extra={
                "workflow_run_id": workflow_run_id,
                "ingestion_execution_id": ingestion_exec.execution_id,
                "ingestion_status": bridge_result["status"],
                "current_phase": final_workflow.current_phase,
                "overall_progress_percent": final_workflow.overall_progress_percent,
            },
        )
        self._refresh_observability_summary(workflow_run_id)

        return final_workflow.to_dict()

    def _apply_ingestion_bridge_result(
        self,
        *,
        workflow_run_id: str,
        ingestion_execution_id: str,
        bridge_result: dict[str, Any],
    ):
        """
        Apply normalized ingestion runtime result to:
        - ingestion child execution metadata
        - parent workflow phase progress
        """
        ingestion_status = bridge_result["status"]
        current_stage = bridge_result["current_stage"]
        completed_stages = bridge_result["completed_stages"]
        total_stages = bridge_result["total_stages"]
        warnings = bridge_result.get("warnings", [])
        errors = bridge_result.get("errors", [])
        artifacts = bridge_result.get("artifacts", [])
        cost_summary = bridge_result.get("cost_summary", {})

        if ingestion_status == "RUNNING":
            self.ingestion_integration_service.update_ingestion_stage(
                ingestion_execution_id,
                current_stage=current_stage,
                completed_stages=completed_stages,
                warnings=warnings,
                artifacts=artifacts,
            )

        elif ingestion_status == "COMPLETED":
            self.ingestion_integration_service.mark_ingestion_completed(
                ingestion_execution_id,
                artifacts=artifacts,
            )

        elif ingestion_status == "FAILED":
            error_code = "INGESTION_FAILED"
            error_message = "Ingestion runtime failed"
            if errors:
                error_code = errors[0].get("code", error_code)
                error_message = errors[0].get("message", error_message)

            self.ingestion_integration_service.mark_ingestion_failed(
                ingestion_execution_id,
                current_stage=current_stage,
                error_code=error_code,
                error_message=error_message,
            )

        workflow = self.workflow_service.get_workflow(workflow_run_id)
        if isinstance(cost_summary, dict):
            existing_summary = workflow.observability_summary or {}
            existing_costs = existing_summary.get("cost_totals", {}) if isinstance(existing_summary, dict) else {}
            ingestion_total = cost_summary.get("total_amount", existing_costs.get("ingestion", 0.0))
            if isinstance(ingestion_total, (int, float)):
                existing_costs["ingestion"] = float(ingestion_total)
            self.workflow_service.update_workflow(
                workflow_run_id,
                {
                    "observability_summary": {
                        **(existing_summary if isinstance(existing_summary, dict) else {}),
                        "cost_totals": existing_costs,
                    }
                },
            )
            workflow = self.workflow_service.get_workflow(workflow_run_id)

        ingestion_progress_percent = int((completed_stages / total_stages) * 100)

        if ingestion_status == "RUNNING":
            progress_snapshot = self.progress_service.update_phase_progress(
                workflow.phases or [],
                "INGESTION",
                ingestion_progress_percent,
            )
            updated = self.workflow_service.update_workflow(
                workflow_run_id,
                {
                    "current_phase": progress_snapshot["current_phase"],
                    "overall_progress_percent": progress_snapshot["overall_progress_percent"],
                    "phases": progress_snapshot["phases"],
                },
            )
            return updated

        if ingestion_status == "COMPLETED":
            progress_snapshot = self.progress_service.mark_phase_completed(
                workflow.phases or [],
                "INGESTION",
            )
            updated = self.workflow_service.update_workflow(
                workflow_run_id,
                {
                    "current_phase": progress_snapshot["current_phase"],
                    "overall_progress_percent": progress_snapshot["overall_progress_percent"],
                    "phases": progress_snapshot["phases"],
                },
            )
            return updated

        if ingestion_status == "FAILED":
            progress_snapshot = self.progress_service.mark_phase_failed(
                workflow.phases or [],
                "INGESTION",
                ingestion_progress_percent,
            )
            failed = self.workflow_service.mark_workflow_failed(
                workflow_run_id,
                error_code="INGESTION_FAILED",
                error_message="Ingestion runtime failed",
            )
            updated = self.workflow_service.update_workflow(
                workflow_run_id,
                {
                    "current_phase": progress_snapshot["current_phase"],
                    "overall_progress_percent": progress_snapshot["overall_progress_percent"],
                    "phases": progress_snapshot["phases"],
                    "status": failed.status,
                    "errors": failed.errors,
                },
            )
            return updated

        return workflow

    def dispatch_workflow_execution(
        self,
        workflow_run_id: str,
        *,
        background_tasks: BackgroundTasks | None = None,
    ) -> dict[str, Any]:
        """
        Dispatch workflow execution asynchronously with hardened failure handling.
        """
        workflow = self.workflow_service.get_workflow(workflow_run_id)
        if not workflow.phases:
            self.prepare_workflow_execution(workflow_run_id)

        dispatch_mode = self.task_dispatcher.dispatch(
            self.execute_workflow_skeleton,
            workflow_run_id,
            background_tasks=background_tasks,
            on_error=lambda exc: self.handle_workflow_failure(
                workflow_run_id,
                exc,
                phase="WORKFLOW",
            ),
        )

        logger.info(
            "Workflow execution dispatched",
            extra={
                "workflow_run_id": workflow_run_id,
                "dispatch_mode": dispatch_mode,
            },
        )

        return {
            "workflow_run_id": workflow_run_id,
            "dispatch_mode": dispatch_mode,
            "status": "RUNNING",
        }