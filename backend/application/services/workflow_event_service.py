"""
Application service for workflow SSE event streaming.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import AsyncGenerator

from backend.application.dto.workflow_event_dto import WorkflowEventDTO
from collections import deque

class WorkflowEventService:
    """
    In-memory event broker for workflow SSE streams.
    """

   
    def __init__(self) -> None:
            self._subscribers = defaultdict(list)
            self._sequence_by_workflow = defaultdict(int)
            self._recent_events: dict[str, deque] = defaultdict(lambda: deque(maxlen=100))


    def subscribe(self, workflow_run_id: str) -> asyncio.Queue[WorkflowEventDTO]:
        queue: asyncio.Queue[WorkflowEventDTO] = asyncio.Queue()
        self._subscribers[workflow_run_id].append(queue)
        return queue

    def unsubscribe(self, workflow_run_id: str, queue: asyncio.Queue[WorkflowEventDTO]) -> None:
        subscribers = self._subscribers.get(workflow_run_id, [])
        if queue in subscribers:
            subscribers.remove(queue)

        if not subscribers and workflow_run_id in self._subscribers:
            self._subscribers.pop(workflow_run_id, None)

    async def publish(
        self,
        *,
        workflow_run_id: str,
        event_type: str,
        phase: str | None = None,
        payload: dict | None = None,
    ) -> WorkflowEventDTO:
        self._sequence_by_workflow[workflow_run_id] += 1

        event = WorkflowEventDTO(
            workflow_run_id=workflow_run_id,
            event_type=event_type,
            phase=phase,
            sequence=self._sequence_by_workflow[workflow_run_id],
            payload=payload or {},
        )

        self._recent_events[workflow_run_id].append(event)

        for queue in list(self._subscribers.get(workflow_run_id, [])):
            await queue.put(event)

        return event

    async def stream(
        self,
        workflow_run_id: str,
        *,
        heartbeat_seconds: int = 15,
    ) -> AsyncGenerator[str, None]:
        """
        Stream workflow events as SSE text chunks.
        """
        queue = self.subscribe(workflow_run_id)

        try:
            # Initial connected event
            connected = WorkflowEventDTO(
                workflow_run_id=workflow_run_id,
                event_type="workflow.connected",
                phase=None,
                sequence=0,
                payload={"message": "SSE stream connected"},
            )
            yield connected.to_sse()

            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=heartbeat_seconds)
                    yield event.to_sse()
                except asyncio.TimeoutError:
                    # SSE heartbeat comment
                    yield ": heartbeat\n\n"
        finally:
            self.unsubscribe(workflow_run_id, queue)

    def get_recent_events(self, workflow_run_id: str, limit: int = 20) -> list[WorkflowEventDTO]:
        events = list(self._recent_events.get(workflow_run_id, []))
        return events[-limit:]


# Singleton event service for now
_workflow_event_service = WorkflowEventService()


def get_workflow_event_service() -> WorkflowEventService:
    return _workflow_event_service