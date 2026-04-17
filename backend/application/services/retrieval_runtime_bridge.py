"""
Backend-facing bridge for section-level retrieval runtime.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from backend.core.exceptions import ConfigurationError, ValidationError


class RetrievalRuntimeBridge:
    """
    Bridge between backend application services and the real retrieval runtime.
    """

    def __init__(
        self,
        retrieval_runner: Callable[..., Any] | None = None,
    ) -> None:
        self.retrieval_runner = retrieval_runner

    def is_available(self) -> bool:
        return self.retrieval_runner is not None

    async def run_retrieval(
        self,
        *,
        section_id: str,
        title: str,
        retrieval_profile: str,
        generation_strategy: str,
        workflow_run_id: str | None = None,
        document_id: str | None = None,
        template_id: str | None = None,
        dependencies: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        runner = self.retrieval_runner or self._build_default_runtime_callable()

        result = runner(
            section_id=section_id,
            title=title,
            retrieval_profile=retrieval_profile,
            generation_strategy=generation_strategy,
            workflow_run_id=workflow_run_id,
            document_id=document_id,
            template_id=template_id,
            dependencies=dependencies or [],
            metadata=metadata or {},
        )

        if inspect.isawaitable(result):
            result = await result

        return self._normalize_result(
            result=result,
            section_id=section_id,
            retrieval_profile=retrieval_profile,
        )

    def _build_default_runtime_callable(self) -> Callable[..., Any]:
        """
        Build the default retrieval runtime callable.

        The real RetrievalService requires a configured VectorSearchService
        (Azure AI Search) and accepts a RetrievalRequest Pydantic model.
        Without vector search configuration, we raise a clear error.
        """
        try:
            import backend.modules.retrieval.services.retrieval_service  # noqa: F401
        except Exception as exc:
            raise ConfigurationError(
                message=(
                    "Failed to import the retrieval runtime entrypoint. "
                    "Ensure the retrieval module is available."
                ),
                error_code="RETRIEVAL_RUNTIME_IMPORT_FAILED",
                details={"reason": str(exc)},
            ) from exc

        # Check if vector search can be wired
        try:
            from backend.modules.retrieval.live_wiring import (
                build_retrieval_runtime,
            )
        except ImportError:
            # Live wiring not available — provide a stub
            async def _unavailable_runner(**kwargs):
                raise ConfigurationError(
                    message=(
                        "Retrieval runtime requires a configured vector search backend "
                        "(e.g., Azure AI Search). Configure the retrieval module's "
                        "live_wiring to enable this feature."
                    ),
                    error_code="RETRIEVAL_RUNTIME_NOT_CONFIGURED",
                    details={
                        "section_id": kwargs.get("section_id"),
                        "hint": "Configure AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_API_KEY environment variables",
                    },
                )
            return _unavailable_runner

        async def _runner(
            *,
            section_id: str,
            title: str,
            retrieval_profile: str,
            generation_strategy: str,
            workflow_run_id: str | None = None,
            document_id: str | None = None,
            template_id: str | None = None,
            dependencies: list[str] | None = None,
            metadata: dict[str, Any] | None = None,
        ):
            try:
                runtime = build_retrieval_runtime()
                service = runtime.retrieval_service
            except Exception as e:
                raise ConfigurationError(
                    message="Failed to build retrieval service from live wiring.",
                    error_code="RETRIEVAL_RUNTIME_INIT_FAILED",
                    details={"error": str(e)},
                )

            from backend.modules.retrieval.contracts.retrieval_contracts import (
                RetrievalRequest,
            )
            import uuid

            request = RetrievalRequest(
                retrieval_id=f"ret_{uuid.uuid4().hex[:12]}",
                project_id=workflow_run_id or document_id or "retrieval_project",
                target_section_id=section_id,
                section_heading=title,
                profile_name=retrieval_profile,
                section_intent=(metadata.get("section_intent") if metadata else None) or title,
                semantic_role="SOURCE",
            )

            evidence_bundle, diagnostics, status = service.retrieve(request)

            return {
                "status": status.value if hasattr(status, "value") else str(status),
                "overall_confidence": diagnostics.final_confidence if hasattr(diagnostics, "final_confidence") else 0.0,
                "evidence_bundle": evidence_bundle.model_dump() if hasattr(evidence_bundle, "model_dump") else evidence_bundle,
                "diagnostics": diagnostics.model_dump() if hasattr(diagnostics, "model_dump") else {},
                "warnings": [],
                "errors": [],
            }

        return _runner

    def _normalize_result(
        self,
        *,
        result: Any,
        section_id: str,
        retrieval_profile: str,
    ) -> dict[str, Any]:
        if isinstance(result, dict):
            normalized = {
                "section_id": section_id,
                "retrieval_profile": retrieval_profile,
                "status": result.get("status"),
                "stage": "retrieval",
                "overall_confidence": float(result.get("overall_confidence", 0.0)),
                # IMPORTANT: keep evidence_bundle as None if missing,
                # so validation can catch invalid retrieval results.
                "evidence_bundle": result.get("evidence_bundle"),
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
                "retrieval_profile": retrieval_profile,
                "status": getattr(result, "status", None),
                "stage": "retrieval",
                "overall_confidence": float(getattr(result, "overall_confidence", 0.0)),
                # IMPORTANT: keep evidence_bundle as None if missing,
                # so validation can catch invalid retrieval results.
                "evidence_bundle": getattr(result, "evidence_bundle", None),
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
                message="Retrieval result is missing required field: section_id",
                error_code="RETRIEVAL_RESULT_INVALID",
                details={"missing_fields": ["section_id"]},
            )

        if normalized.get("status") is None:
            raise ValidationError(
                message="Retrieval result is missing required field: status",
                error_code="RETRIEVAL_RESULT_INVALID",
                details={"missing_fields": ["status"]},
            )

        if normalized.get("evidence_bundle") is None:
            raise ValidationError(
                message="Retrieval result is missing required field: evidence_bundle",
                error_code="RETRIEVAL_RESULT_INVALID",
                details={"missing_fields": ["evidence_bundle"]},
            )