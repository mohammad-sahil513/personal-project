"""
Tests for request correlation context vars.
"""

from __future__ import annotations

from backend.core.request_context import (
    clear_request_id,
    generate_request_id,
    get_request_id,
    set_request_id,
)


def test_request_context_lifecycle():
    assert get_request_id() is None
    
    req_id = generate_request_id()
    assert req_id.startswith("req_")
    
    set_request_id(req_id)
    assert get_request_id() == req_id
    
    clear_request_id()
    assert get_request_id() is None
