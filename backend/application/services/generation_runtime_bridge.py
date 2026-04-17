"""
Backend-facing bridge for section-level generation runtime.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from backend.core.exceptions import ConfigurationError, ValidationError
from backend.core.ids import generate_workflow_run_id


class GenerationRuntimeBridge:
    """
    Bridge between backend application services and the real generation runtime.
    """

    def __init__(
        self,
        generation_runner: Callable[..., Any] | None = None,
    ) -> None:
        self.generation_runner = generation_runner

    def is_available(self) -> bool:
        return self.generation_runner is not None

    async def run_generation(
        self,
        *,
        section_id: str,
        title: str,
        generation_strategy: str,
        retrieval_result: dict[str, Any],
        workflow_run_id: str | None = None,
        document_id: str | None = None,
        template_id: str | None = None,
        template_version: str | None = None,
        dependencies: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        runner = self.generation_runner or self._build_default_runtime_callable()

        result = runner(
            section_id=section_id,
            title=title,
            generation_strategy=generation_strategy,
            retrieval_result=retrieval_result,
            workflow_run_id=workflow_run_id,
            document_id=document_id,
            template_id=template_id,
            template_version=template_version,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )

        if inspect.isawaitable(result):
            result = await result

        return self._normalize_result(
            result=result,
            section_id=section_id,
            generation_strategy=generation_strategy,
        )

    def _build_default_runtime_callable(self) -> Callable[..., Any]:
        """
        Build a default callable wired through Generation SectionExecutor.
        """
        try:
            from backend.modules.generation.live_wiring import (
                build_generation_runtime_callable,
            )
        except Exception as exc:
            raise ConfigurationError(
                message=(
                    "Failed to import generation live wiring. "
                    "Ensure backend.modules.generation.live_wiring is available."
                ),
                error_code="GENERATION_RUNTIME_IMPORT_FAILED",
                details={"reason": str(exc)},
            ) from exc

        return build_generation_runtime_callable(
            output_type_mapper=self._map_output_type,
        )

    def _map_output_type(self, generation_strategy: str) -> str:
        normalized = (generation_strategy or "").strip().lower()
        if normalized == "generate_table":
            return "markdown_table"
        if normalized == "diagram_plantuml":
            return "diagram_artifact"
        return "markdown_text"


    def _normalize_result(
        self,
        *,
        result: Any,
        section_id: str,
        generation_strategy: str,
    ) -> dict[str, Any]:
        if isinstance(result, dict):
            normalized = {
                "section_id": section_id,
                "generation_strategy": generation_strategy,
                "status": result.get("status"),
                "stage": "generation",
                "output_type": result.get("output_type"),
                "content": result.get("content"),
                "artifacts": result.get("artifacts", []),
                "diagnostics": result.get("diagnostics", {}),
                "warnings": result.get("warnings", []),
                "errors": result.get("errors", []),
                "request_id": result.get("request_id"),
                "workflow_run_id": result.get("workflow_run_id"),
                "document_id": result.get("document_id"),
                "template_id": result.get("template_id"),
            }
        else:
            normalized = {
                "section_id": section_id,
                "generation_strategy": generation_strategy,
                "status": getattr(result, "status", None),
                "stage": "generation",
                "output_type": getattr(result, "output_type", None),
                "content": getattr(result, "content", None),
                "artifacts": getattr(result, "artifacts", []),
                "diagnostics": getattr(result, "diagnostics", {}),
                "warnings": getattr(result, "warnings", []),
                "errors": getattr(result, "errors", []),
                "request_id": getattr(result, "request_id", None),
                "workflow_run_id": getattr(result, "workflow_run_id", None),
                "document_id": getattr(result, "document_id", None),
                "template_id": getattr(result, "template_id", None),
            }

        self._validate_normalized_result(normalized)
        return normalized

    def _validate_normalized_result(self, normalized: dict[str, Any]) -> None:
        if not normalized.get("section_id"):
            raise ValidationError(
                message="Generation result is missing required field: section_id",
                error_code="GENERATION_RESULT_INVALID",
                details={"missing_fields": ["section_id"]},
            )

        if normalized.get("status") is None:
            raise ValidationError(
                message="Generation result is missing required field: status",
                error_code="GENERATION_RESULT_INVALID",
                details={"missing_fields": ["status"]},
            )

        if normalized.get("output_type") is None:
            raise ValidationError(
                message="Generation result is missing required field: output_type",
                error_code="GENERATION_RESULT_INVALID",
                details={"missing_fields": ["output_type"]},
            )

        has_content = normalized.get("content") is not None
        has_artifacts = len(normalized.get("artifacts", [])) > 0

        if not has_content and not has_artifacts:
            raise ValidationError(
                message="Generation result must include content or artifacts",
                error_code="GENERATION_RESULT_INVALID",
                details={"required_one_of": ["content", "artifacts"]},
            )