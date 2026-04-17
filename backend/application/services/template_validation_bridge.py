"""
Backend-facing bridge for template validation runtime.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from backend.core.exceptions import ConfigurationError, ValidationError


class TemplateValidationBridge:
    """
    Bridge between backend application services and the real template validation runtime.
    """

    def __init__(
        self,
        validate_runner: Callable[..., Any] | None = None,
    ) -> None:
        self.validate_runner = validate_runner

    async def run_validation(
        self,
        *,
        template_id: str,
        filename: str,
        template_type: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        runner = self.validate_runner or self._build_default_runtime_callable()

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
        Build the default callable for template validation.
        """
        try:
            from backend.modules.template.live_wiring import (
                build_template_validation_runtime_callable,
            )
            return build_template_validation_runtime_callable()
        except Exception as exc:
            if isinstance(exc, ConfigurationError):
                raise
            raise ConfigurationError(
                message=(
                    "Failed to import template live wiring. "
                    "Ensure backend.modules.template.live_wiring is available."
                ),
                error_code="TEMPLATE_VALIDATION_IMPORT_FAILED",
                details={"reason": str(exc)},
            ) from exc

    def _normalize_result(self, result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            normalized = {
                "is_valid": result.get("is_valid"),
                "errors": result.get("errors", []),
                "warnings": result.get("warnings", []),
            }
        else:
            normalized = {
                "is_valid": getattr(result, "is_valid", None),
                "errors": getattr(result, "errors", []),
                "warnings": getattr(result, "warnings", []),
            }

        if normalized["is_valid"] is None:
            raise ValidationError(
                message="Template validation result is missing required field: is_valid",
                error_code="TEMPLATE_VALIDATION_INVALID",
                details={"missing_fields": ["is_valid"]},
            )

        return normalized