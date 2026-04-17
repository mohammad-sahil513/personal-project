"""
Backend-facing bridge for template resolution runtime.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from backend.core.exceptions import ConfigurationError, ValidationError


class TemplateResolveBridge:
    """
    Bridge between backend application services and the real template resolve runtime.
    """

    def __init__(
        self,
        resolve_runner: Callable[..., Any] | None = None,
    ) -> None:
        self.resolve_runner = resolve_runner

    async def run_resolve(
        self,
        *,
        template_id: str,
        filename: str,
        template_type: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        runner = self.resolve_runner or self._build_default_runtime_callable()

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
        Build the default template resolve runtime callable.
        """
        try:
            from backend.modules.template.live_wiring import (
                build_template_resolve_runtime_callable,
            )
            return build_template_resolve_runtime_callable()
        except Exception as exc:
            if isinstance(exc, ConfigurationError):
                raise
            raise ConfigurationError(
                message=(
                    "Failed to import template live wiring. "
                    "Ensure backend.modules.template.live_wiring is available."
                ),
                error_code="TEMPLATE_RESOLVE_IMPORT_FAILED",
                details={"reason": str(exc)},
            ) from exc

    def _normalize_result(self, result: Any) -> dict[str, Any]:
        if isinstance(result, dict):
            normalized = {
                "resolved_sections": result.get("resolved_sections"),
            }
        else:
            normalized = {
                "resolved_sections": getattr(result, "resolved_sections", None),
            }

        if normalized["resolved_sections"] is None:
            raise ValidationError(
                message="Template resolve result is missing required field: resolved_sections",
                error_code="TEMPLATE_RESOLVE_INVALID",
                details={"missing_fields": ["resolved_sections"]},
            )

        return normalized