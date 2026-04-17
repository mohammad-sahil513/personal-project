"""
Shared structured logging service for the observability module.

Responsibilities:
- Emit structured JSON logs
- Standardize common observability/correlation fields
- Provide convenience methods for info / warning / error events

Important:
- This file is logging-only.
- It does NOT manage request context storage.
- It does NOT estimate or aggregate cost.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class LoggingService:
    """
    Minimal structured logging wrapper.

    Design goals:
    - use standard library logging for portability
    - emit JSON payloads as log messages
    - support optional context provider injection
    - keep a stable event shape for downstream parsing/tests
    """

    def __init__(
        self,
        logger_name: str = "observability",
        *,
        level: int = logging.INFO,
        context_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.logger = logging.getLogger(logger_name)
        self.logger.setLevel(level)
        self.context_provider = context_provider

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def info(self, event: str, **fields: Any) -> dict[str, Any]:
        """
        Emit an INFO log event and return the structured payload.
        """
        return self.log("info", event, **fields)

    def warning(self, event: str, **fields: Any) -> dict[str, Any]:
        """
        Emit a WARNING log event and return the structured payload.
        """
        return self.log("warning", event, **fields)

    def error(self, event: str, **fields: Any) -> dict[str, Any]:
        """
        Emit an ERROR log event and return the structured payload.
        """
        return self.log("error", event, **fields)

    def log(self, level: str, event: str, **fields: Any) -> dict[str, Any]:
        """
        Emit one structured log event.

        Stable payload shape:
        {
          "timestamp": "...",
          "level": "info|warning|error",
          "event": "event_name",
          ...context fields...,
          ...custom fields...
        }
        """
        if not event or not event.strip():
            raise ValueError("event cannot be empty.")

        payload = self._build_payload(level=level, event=event, **fields)
        message = json.dumps(payload, ensure_ascii=False, default=str)

        if level == "info":
            self.logger.info(message)
        elif level == "warning":
            self.logger.warning(message)
        elif level == "error":
            self.logger.error(message)
        else:
            raise ValueError(f"Unsupported log level: {level!r}")

        return payload

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_payload(self, *, level: str, event: str, **fields: Any) -> dict[str, Any]:
        """
        Build a structured payload by merging:
        - standard fields
        - optional shared context
        - explicit event fields (explicit fields override context keys)
        """
        payload: dict[str, Any] = {
            "timestamp": utc_now_iso(),
            "level": level,
            "event": event,
        }

        context = self.context_provider() if self.context_provider is not None else {}
        if context:
            payload.update(context)

        payload.update(fields)
        return payload