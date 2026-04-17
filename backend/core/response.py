"""
Standard API response helpers.
"""

from __future__ import annotations

from typing import Any


def success_response(
    message: str,
    data: Any = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a successful API response envelope.
    """
    return {
        "success": True,
        "message": message,
        "data": data,
        "errors": [],
        "meta": meta or {},
    }


def error_response(
    message: str,
    errors: list[dict[str, Any]] | None = None,
    data: Any = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a failure API response envelope.
    """
    return {
        "success": False,
        "message": message,
        "data": data,
        "errors": errors or [],
        "meta": meta or {},
    }