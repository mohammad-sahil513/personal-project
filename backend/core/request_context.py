"""
Request-scoped correlation ID helpers.
"""

from __future__ import annotations

from contextvars import ContextVar
from uuid import uuid4


_request_id_ctx_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def generate_request_id() -> str:
    return f"req_{uuid4().hex[:12]}"


def set_request_id(request_id: str) -> None:
    _request_id_ctx_var.set(request_id)


def get_request_id() -> str | None:
    return _request_id_ctx_var.get()


def clear_request_id() -> None:
    _request_id_ctx_var.set(None)