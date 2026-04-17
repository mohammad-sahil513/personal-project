"""
Backend adapter for wiring the real ingestion orchestrator into the workflow layer.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from backend.application.services.ingestion_integration_service import INGESTION_STAGE_ORDER
from backend.core.exceptions import ConfigurationError, ValidationError


class RealIngestionOrchestratorAdapter:
    """
    Adapter that invokes the real ingestion runtime and normalizes the result
    into a backend-friendly bridge shape.

    Notes:
    - By default, this adapter tries to wire to the current project's
      observed ingestion orchestrator entrypoint.
    - If your exact runtime entrypoint or signature differs, only update
      `_build_default_runtime_callable()`.
    """

    def __init__(
        self,
        runtime_callable: Callable[..., Any] | None = None,
    ) -> None:
        self.runtime_callable = runtime_callable

    async def run(
        self,
        *,
        workflow_run_id: str,
        document_id: str,
        ingestion_execution_id: str,
    ) -> dict[str, Any]:
        """
        Run the real ingestion runtime and return a normalized bridge result.
        """
        runtime_callable = self.runtime_callable or self._build_default_runtime_callable()

        result = runtime_callable(
            workflow_run_id=workflow_run_id,
            document_id=document_id,
            ingestion_execution_id=ingestion_execution_id,
        )

        if inspect.isawaitable(result):
            result = await result

        return self._normalize_pipeline_result(result)

    def _build_default_runtime_callable(self) -> Callable[..., Any]:
        """
        Build the default runtime callable using the current project's ingestion runtime.
        """
        try:
            from backend.modules.ingestion.live_wiring import build_ingestion_runtime
        except Exception as exc:
            raise ConfigurationError(
                message=(
                    "Failed to import the real ingestion runtime entrypoint. "
                    "Ensure backend.modules.ingestion.live_wiring is available."
                ),
                error_code="INGESTION_RUNTIME_IMPORT_FAILED",
                details={"reason": str(exc)},
            ) from exc

        async def _runner(
            *,
            workflow_run_id: str,
            document_id: str,
            ingestion_execution_id: str,
        ):
            try:
                runtime = build_ingestion_runtime()
            except Exception as exc:
                raise ConfigurationError(
                    message="Failed to build ingestion runtime from live wiring.",
                    error_code="INGESTION_RUNTIME_INIT_FAILED",
                    details={"reason": str(exc)},
                ) from exc

            return await runtime.run_ingestion(
                workflow_run_id=workflow_run_id,
                document_id=document_id,
                ingestion_execution_id=ingestion_execution_id,
            )

        return _runner

    def _normalize_pipeline_result(self, result: Any) -> dict[str, Any]:
        """
        Normalize a real ingestion runtime result into the backend bridge shape.
        """
        status = self._read_value(result, "status")
        raw_status = str(status or "").upper()
        
        stage_outputs = {}
        warnings = []
        errors = []
        artifacts = []

        # Iterate over possible stages output (1 to 9) to extract nested warnings & artifacts
        for i in range(1, 10):
            stage_out = self._read_value(result, f"stage_{i}_output")
            if stage_out:
                if i - 1 < len(INGESTION_STAGE_ORDER):
                    stage_name = INGESTION_STAGE_ORDER[i - 1]
                    stage_outputs[stage_name] = stage_out
                
                # Aggregate nested warnings
                stage_warnings = self._read_value(stage_out, "warnings", default=[])
                if stage_warnings:
                    for w in stage_warnings:
                        if hasattr(w, "model_dump"):
                            warnings.append(w.model_dump())
                        elif hasattr(w, "dict"):
                            warnings.append(w.dict())
                        else:
                            warnings.append(w)
                            
                # Aggregate nested artifacts if they exist
                stage_artifacts = self._read_value(stage_out, "artifacts", default=[])
                if stage_artifacts:
                    artifacts.extend(stage_artifacts)

        completed_stages = self._read_value(result, "completed_stages", default=None)
        current_stage = self._read_value(result, "current_stage", default=None)

        bridge_status = self._map_pipeline_status(status)

        # Special handling for duplicate short-circuit.
        if raw_status == "DUPLICATE_SKIPPED":
            warnings.append(
                {
                    "code": "INGESTION_DUPLICATE_SKIPPED",
                    "message": "Document was detected as a duplicate and ingestion was short-circuited",
                }
            )

        # For RUNNING results, require at least one real progress signal.
        if bridge_status == "RUNNING":
            has_progress_signal = (
                current_stage is not None
                or completed_stages is not None
                or (isinstance(stage_outputs, dict) and len(stage_outputs) > 0)
            )
            if not has_progress_signal:
                raise ValidationError(
                    message="RUNNING ingestion result must include progress information",
                    error_code="INGESTION_RESULT_INVALID",
                    details={
                        "required_one_of": [
                            "current_stage",
                            "completed_stages",
                            "stage_outputs",
                        ]
                    },
                )

        if completed_stages is None:
            completed_stages = self._infer_completed_stages(stage_outputs, status, bridge_status)

        total_stages = len(INGESTION_STAGE_ORDER)

        if current_stage is None:
            current_stage = self._infer_current_stage(
                completed_stages=completed_stages,
                bridge_status=bridge_status,
            )

        normalized = {
            "status": bridge_status,
            "current_stage": current_stage,
            "completed_stages": completed_stages,
            "total_stages": total_stages,
            "warnings": warnings,
            "errors": errors,
            "artifacts": artifacts,
        }

        self._validate_normalized_result(normalized)
        return normalized

    def _map_pipeline_status(self, status: Any) -> str:
        value = str(status or "FAILED").upper()

        if value in {"COMPLETED", "DUPLICATE_SKIPPED"}:
            return "COMPLETED"

        if value in {"FAILED", "VALIDATION_BLOCKED"}:
            return "FAILED"

        return "RUNNING"

    def _infer_completed_stages(
        self,
        stage_outputs: dict[str, Any],
        status: Any,
        bridge_status: str,
    ) -> int:
        status_value = str(status or "").upper()

        if status_value == "DUPLICATE_SKIPPED":
            return len(INGESTION_STAGE_ORDER)

        if bridge_status == "COMPLETED":
            return len(INGESTION_STAGE_ORDER)

        if not isinstance(stage_outputs, dict):
            return 0

        completed = 0
        for stage_name in INGESTION_STAGE_ORDER:
            stage_result = stage_outputs.get(stage_name)
            if stage_result is not None:
                completed += 1

        return completed

    def _infer_current_stage(
        self,
        *,
        completed_stages: int,
        bridge_status: str,
    ) -> str:
        if bridge_status == "COMPLETED":
            return INGESTION_STAGE_ORDER[-1]

        if completed_stages < 0:
            completed_stages = 0

        if completed_stages >= len(INGESTION_STAGE_ORDER):
            return INGESTION_STAGE_ORDER[-1]

        return INGESTION_STAGE_ORDER[completed_stages]

    def _validate_normalized_result(self, normalized: dict[str, Any]) -> None:
        required = ["status", "current_stage", "completed_stages", "total_stages"]
        missing = [field for field in required if normalized.get(field) is None]

        if missing:
            raise ValidationError(
                message="Normalized ingestion runtime result is missing required fields",
                error_code="INGESTION_RESULT_INVALID",
                details={"missing_fields": missing},
            )

        if normalized["total_stages"] <= 0:
            raise ValidationError(
                message="total_stages must be greater than zero",
                error_code="INGESTION_RESULT_INVALID",
                details={"field": "total_stages"},
            )

        if normalized["completed_stages"] < 0:
            raise ValidationError(
                message="completed_stages must be greater than or equal to zero",
                error_code="INGESTION_RESULT_INVALID",
                details={"field": "completed_stages"},
            )

    def _read_value(self, source: Any, name: str, default: Any = None) -> Any:
        if isinstance(source, dict):
            return source.get(name, default)
        return getattr(source, name, default)