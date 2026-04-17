"""
Shared request/context service for observability.

Responsibilities:
- Hold correlation context for the current logical execution flow
- Support job/document/template/section context keys
- Provide simple start/update/get/clear APIs

Important:
- This file is context-only.
- It does NOT emit logs.
- It does NOT estimate or aggregate cost.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.request_context import get_request_id


class RequestContext(BaseModel):
    """
    Shared correlation context for observability.

    These fields are aligned to the Generation observability requirements and
    the full-system correlation continuity model.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str | None = Field(default=None)
    workflow_run_id: str | None = Field(default=None)
    request_id: str | None = Field(default=None)
    document_id: str | None = Field(default=None)
    template_id: str | None = Field(default=None)
    template_version: str | None = Field(default=None)
    section_id: str | None = Field(default=None)

    def as_dict(self, *, exclude_none: bool = True) -> dict[str, Any]:
        """
        Return the current context as a plain dictionary.
        """
        return self.model_dump(exclude_none=exclude_none)


class RequestContextService:
    """
    Context-local observability correlation service.

    Uses `contextvars` so the context is safe across async tasks and request flows
    within the current process.
    """

    _context_var: ContextVar[RequestContext] = ContextVar(
        "request_context",
        default=RequestContext(),
    )

    # ------------------------------------------------------------------
    # Job-level context lifecycle
    # ------------------------------------------------------------------

    def start_job_context(
        self,
        *,
        job_id: str | None = None,
        document_id: str | None = None,
        template_id: str | None = None,
        template_version: str | None = None,
        section_id: str | None = None,
    ) -> RequestContext:
        """
        Replace the current context with a fresh job-level context.
        """
        context = RequestContext(
            job_id=job_id,
            workflow_run_id=job_id,
            request_id=get_request_id(),
            document_id=document_id,
            template_id=template_id,
            template_version=template_version,
            section_id=section_id,
        )
        self._context_var.set(context)
        return context

    def clear_context(self) -> None:
        """
        Reset the current context to an empty state.
        """
        self._context_var.set(RequestContext())

    # ------------------------------------------------------------------
    # Context updates
    # ------------------------------------------------------------------

    def set_section_context(self, section_id: str | None) -> RequestContext:
        """
        Set or clear only the section_id on the current context.
        """
        current = self.get_context()
        updated = current.model_copy(update={"section_id": section_id})
        self._context_var.set(updated)
        return updated

    def update_context(self, **fields: Any) -> RequestContext:
        """
        Partially update the current context with supplied fields.

        Allowed keys:
        - job_id
        - workflow_run_id
        - request_id
        - document_id
        - template_id
        - template_version
        - section_id
        """
        current = self.get_context()
        updated = current.model_copy(update=fields)
        self._context_var.set(updated)
        return updated

    # ------------------------------------------------------------------
    # Context access
    # ------------------------------------------------------------------

    def get_context(self) -> RequestContext:
        """
        Return the current context object.
        """
        return self._context_var.get()

    def get_context_dict(self, *, exclude_none: bool = True) -> dict[str, Any]:
        """
        Return the current context as a plain dictionary.
        """
        return self.get_context().as_dict(exclude_none=exclude_none)