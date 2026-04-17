"""
Shared backend logging utilities.
"""

from __future__ import annotations

import logging
from typing import Optional

from backend.core.config import get_settings
from backend.core.request_context import get_request_id

_LOGGING_CONFIGURED = False


class RequestIdFilter(logging.Filter):
    """
    Inject request_id from request context into log records.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def configure_logging(level: Optional[str] = None) -> None:
    """
    Configure application-wide logging.

    Safe to call multiple times.
    """
    global _LOGGING_CONFIGURED

    if _LOGGING_CONFIGURED:
        return

    settings = get_settings()
    log_level = (level or settings.log_level).upper()

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | request_id=%(request_id)s | %(message)s",
    )

    request_filter = RequestIdFilter()
    root_logger = logging.getLogger()

    for handler in root_logger.handlers:
        handler.addFilter(request_filter)

    _LOGGING_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """
    Return a configured logger instance.
    """
    configure_logging()
    return logging.getLogger(name)