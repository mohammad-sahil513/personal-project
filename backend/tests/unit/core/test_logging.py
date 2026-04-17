"""
Tests for structured logging utilities.
"""

from __future__ import annotations

import logging
from backend.core.logging import RequestIdFilter, configure_logging, get_logger
from backend.core.request_context import set_request_id, clear_request_id


def test_request_id_filter():
    record = logging.LogRecord("name", logging.INFO, "file", 10, "msg", (), None)
    filter_ = RequestIdFilter()
    
    # Context empty
    clear_request_id()
    filter_.filter(record)
    assert record.request_id == "-"
    
    # Context set
    set_request_id("test_req_123")
    try:
        filter_.filter(record)
        assert record.request_id == "test_req_123"
    finally:
        clear_request_id()


def test_configure_logging_idempotent():
    # Will toggle global _LOGGING_CONFIGURED flag inside the module.
    configure_logging("DEBUG")
    logger = logging.getLogger()
    assert any(isinstance(f, RequestIdFilter) for h in logger.handlers for f in h.filters)

    # Calling it again shouldn't break or crash
    configure_logging("INFO")


def test_get_logger():
    logger = get_logger("test.logger")
    assert logger.name == "test.logger"
