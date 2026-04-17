"""
Backend-facing bridge for real ingestion runtime execution.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from backend.application.services.ingestion_integration_service import INGESTION_STAGE_ORDER
from backend.core.exceptions import ConfigurationError, ValidationError


class IngestionRuntimeBridge:
    """
    Bridge between the backend workflow layer and the real ingestion runtime.

    The bridge accepts an injected runner function/callable and normalizes the
    result into a backend-friendly shape.
    """

    def __init__(
        self,
        ingestion_runner: Callable[..., Any] | None = None,
    ) -> None:
        self.ingestion_runner = ingestion_runner

    def is_available(self) -> bool:
        return self.ingestion_runner is not None

    def _build_default_runtime_callable(self) -> Callable[..., Any]:
        """
        Build the default ingestion runtime callable from module live wiring.
        """
        try:
            from backend.modules.ingestion.live_wiring import build_ingestion_runtime
        except Exception as exc:
            raise ConfigurationError(
                message=(
                    "Failed to import ingestion live wiring. "
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
        ) -> Any:
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

    async def run_ingestion(
        self,
        *,
        workflow_run_id: str,
        document_id: str,
        ingestion_execution_id: str,
    ) -> dict[str, Any]:
        """
        Execute the real ingestion runtime and normalize its result.
        """
        runner = self.ingestion_runner or self._build_default_runtime_callable()

        result = runner(
            workflow_run_id=workflow_run_id,
            document_id=document_id,
            ingestion_execution_id=ingestion_execution_id,
        )

        if inspect.isawaitable(result):
            result = await result

        return self._normalize_result(result)

    def _normalize_result(self, result: Any) -> dict[str, Any]:
        """
        Normalize a bridge/orchestrator result into a backend-friendly dict.
        Supported input:
        - dict
        - object with matching attributes
        """
        if isinstance(result, dict):
            normalized = {
                "status": result.get("status"),
                "stage": "ingestion",
                "current_stage": result.get("current_stage"),
                "completed_stages": result.get("completed_stages"),
                "total_stages": result.get("total_stages", len(INGESTION_STAGE_ORDER)),
                "warnings": result.get("warnings", []),
                "errors": result.get("errors", []),
                "artifacts": result.get("artifacts", []),
                "cost_summary": result.get("cost_summary", {}),
                "request_id": result.get("request_id"),
                "workflow_run_id": result.get("workflow_run_id"),
                "document_id": result.get("document_id"),
                "template_id": result.get("template_id"),
                "section_id": result.get("section_id"),
            }
        else:
            normalized = {
                "status": getattr(result, "status", None),
                "stage": "ingestion",
                "current_stage": getattr(result, "current_stage", None),
                "completed_stages": getattr(result, "completed_stages", None),
                "total_stages": getattr(result, "total_stages", len(INGESTION_STAGE_ORDER)),
                "warnings": getattr(result, "warnings", []),
                "errors": getattr(result, "errors", []),
                "artifacts": getattr(result, "artifacts", []),
                "cost_summary": getattr(result, "cost_summary", {}),
                "request_id": getattr(result, "request_id", None),
                "workflow_run_id": getattr(result, "workflow_run_id", None),
                "document_id": getattr(result, "document_id", None),
                "template_id": getattr(result, "template_id", None),
                "section_id": getattr(result, "section_id", None),
            }

        self._validate_normalized_result(normalized)
        return normalized

    def _validate_normalized_result(self, normalized: dict[str, Any]) -> None:
        required = ["status", "current_stage", "completed_stages", "total_stages"]
        missing = [field for field in required if normalized.get(field) is None]

        if missing:
            raise ValidationError(
                message="Ingestion runtime result is missing required fields",
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