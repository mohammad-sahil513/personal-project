"""
Backend-facing bridge for template compiler runtime execution.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from backend.core.exceptions import ConfigurationError, ValidationError


class TemplateRuntimeBridge:
    """
    Bridge between backend application services and the real template compiler runtime.
    """

    def __init__(
        self,
        compile_runner: Callable[..., Any] | None = None,
    ) -> None:
        self.compile_runner = compile_runner

    def is_available(self) -> bool:
        return self.compile_runner is not None

    async def run_compile(
        self,
        *,
        template_id: str,
        filename: str,
        template_type: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute the real template compiler runtime and normalize its result.
        """
        runner = self.compile_runner or self._build_default_runtime_callable()

        result = runner(
            template_id=template_id,
            filename=filename,
            template_type=template_type,
            version=version,
        )

        if inspect.isawaitable(result):
            result = await result

        return self._normalize_result(result)

    def _build_default_runtime_callable(self) -> Callable[..., Any]:
        """
        Build the default template compiler runtime callable.
        """
        try:
            from backend.modules.template.live_wiring import (
                build_template_compile_runtime_callable,
            )
            return build_template_compile_runtime_callable()
        except Exception as exc:
            if isinstance(exc, ConfigurationError):
                raise
            raise ConfigurationError(
                message=(
                    "Failed to import template live wiring. "
                    "Ensure backend.modules.template.live_wiring is available."
                ),
                error_code="TEMPLATE_RUNTIME_IMPORT_FAILED",
                details={"reason": str(exc)},
            ) from exc

    def _normalize_result(self, result: Any) -> dict[str, Any]:
        """
        Normalize a real template compiler result into a backend-friendly shape.
        """
        if isinstance(result, dict):
            normalized = {
                "status": result.get("status"),
                "compiled_artifacts": result.get("compiled_artifacts", []),
                "warnings": result.get("warnings", []),
                "errors": result.get("errors", []),
            }
        else:
            normalized = {
                "status": getattr(result, "status", None),
                "compiled_artifacts": getattr(result, "compiled_artifacts", []),
                "warnings": getattr(result, "warnings", []),
                "errors": getattr(result, "errors", []),
            }

        self._validate_normalized_result(normalized)
        return normalized

    def _validate_normalized_result(self, normalized: dict[str, Any]) -> None:
        if normalized.get("status") is None:
            raise ValidationError(
                message="Template runtime result is missing required field: status",
                error_code="TEMPLATE_RESULT_INVALID",
                details={"missing_fields": ["status"]},
            )