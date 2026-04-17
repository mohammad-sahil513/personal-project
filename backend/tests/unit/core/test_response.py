"""
Tests for standard API response helpers.
"""

from __future__ import annotations

from backend.core.response import error_response, success_response


def test_success_response():
    resp = success_response(message="OK", data={"id": 1}, meta={"page": 1})
    assert resp["success"] is True
    assert resp["message"] == "OK"
    assert resp["data"] == {"id": 1}
    assert resp["errors"] == []
    assert resp["meta"] == {"page": 1}


def test_error_response():
    errors = [{"code": "BAD", "message": "Failed"}]
    resp = error_response(message="Not OK", errors=errors)
    assert resp["success"] is False
    assert resp["message"] == "Not OK"
    assert resp["data"] is None
    assert resp["errors"] == errors
    assert resp["meta"] == {}
