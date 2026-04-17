"""
SSE publisher for the Generation module.

Responsibilities:
- Publish Generation progress events
- Assign monotonic sequence_id values
- Provide replay-safe event history retrieval
- Serialize events in SSE-compatible wire format

Important:
- This file does NOT execute generation logic.
- This file does NOT perform section orchestration, Retrieval, validation, or export.
- This file is intentionally in-memory and DB-free for the current phase.
"""

from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


class SSEEventType(str, Enum):
    """
    Allowed Generation SSE event types.

    These align with the approved Generation SSE contract.
    """

    SECTION_STARTED = "section_started"
    SECTION_COMPLETED = "section_completed"
    SECTION_FAILED = "section_failed"
    GENERATION_COMPLETED = "generation_completed"
    GENERATION_FAILED = "generation_failed"
    EXPORT_COMPLETED = "export_completed"


class SSEEvent(BaseModel):
    """
    Structured SSE event payload for Generation progress updates.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(description="Stable Generation job identifier.")
    sequence_id: int = Field(
        ge=1,
        description="Monotonic sequence number assigned by the publisher.",
    )
    event: SSEEventType = Field(description="Generation progress event type.")
    timestamp: str = Field(description="Event timestamp in ISO-8601 UTC format.")
    section_id: str | None = Field(
        default=None,
        description="Optional section identifier for section-scoped events.",
    )
    outcome: str | None = Field(
        default=None,
        description="Optional outcome/status summary for the event.",
    )
    data: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional structured event payload.",
    )


class SSEPublisher:
    """
    Centralized, replay-safe in-memory SSE event publisher.

    Design notes:
    - sequence_id is monotonically increasing per publisher instance
    - history is bounded to prevent unbounded memory growth
    - history retrieval supports simple replay since a given sequence_id
    """

    def __init__(self, max_history: int = 5000) -> None:
        if max_history < 1:
            raise ValueError("max_history must be >= 1.")

        self.max_history = max_history
        self._events: deque[SSEEvent] = deque(maxlen=max_history)
        self._next_sequence_id = 1
        self._lock = threading.Lock()

    def publish(
        self,
        *,
        job_id: str,
        event: SSEEventType,
        section_id: str | None = None,
        outcome: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> SSEEvent:
        """
        Publish one Generation SSE event and return the structured event object.
        """
        if not job_id or not job_id.strip():
            raise ValueError("job_id cannot be empty.")

        payload = SSEEvent(
            job_id=job_id,
            sequence_id=self._next_id(),
            event=event,
            timestamp=utc_now_iso(),
            section_id=section_id,
            outcome=outcome,
            data=data or {},
        )

        with self._lock:
            self._events.append(payload)

        return payload

    def get_events_since(
        self,
        *,
        sequence_id: int | None = None,
        job_id: str | None = None,
    ) -> list[SSEEvent]:
        """
        Return all events with sequence_id > given sequence_id.

        Optional job_id filtering is supported for per-job event consumption.
        """
        with self._lock:
            events = list(self._events)

        filtered = []
        for event in events:
            if sequence_id is not None and event.sequence_id <= sequence_id:
                continue
            if job_id is not None and event.job_id != job_id:
                continue
            filtered.append(event)

        return filtered

    def latest_sequence_id(self) -> int:
        """
        Return the latest assigned sequence_id, or 0 if no events were published.
        """
        with self._lock:
            if not self._events:
                return 0
            return self._events[-1].sequence_id

    def to_sse_payload(self, event: SSEEvent) -> str:
        """
        Serialize one structured event into SSE wire format.

        Example:
            id: 12
            event: section_completed
            data: {...}
        """
        data_json = json.dumps(event.model_dump(), ensure_ascii=False)
        return (
            f"id: {event.sequence_id}\n"
            f"event: {event.event.value}\n"
            f"data: {data_json}\n\n"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        """
        Allocate the next monotonic sequence_id.
        """
        with self._lock:
            sequence_id = self._next_sequence_id
            self._next_sequence_id += 1
            return sequence_id