"""
Application DTOs for workflow SSE events.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class WorkflowEventDTO:
    workflow_run_id: str
    event_type: str
    phase: str | None = None
    sequence: int | None = None
    timestamp: str = field(default_factory=_utc_now_iso)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_sse(self) -> str:
        """
        Convert the event into SSE wire format.
        """
        data = self.to_dict()
        return (
            f"event: {self.event_type}\n"
            f"data: {data}\n\n"
        )
