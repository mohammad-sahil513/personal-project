"""
FastAPI routes for the Generation module.

Responsibilities:
- Start a Generation job
- Stream Generation progress events via SSE
- Return Generation job status

Important:
- This file is route-only.
- Business logic lives behind injected services/orchestrators.
- SSE is retained as the live progress channel.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Protocol, runtime_checkable

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from backend.modules.generation.contracts.generation_contracts import (
    GenerationJobRequest,
    GenerationJobResponse,
)
from backend.modules.generation.orchestrators.generation_orchestrator import (
    GenerationOrchestratorResponse,
)
from backend.modules.generation.streaming.sse_publisher import (
    SSEPublisher,
)

router = APIRouter(tags=["generation"])


# ------------------------------------------------------------------------------
# Route service protocol
# ------------------------------------------------------------------------------


@runtime_checkable
class GenerationRouteService(Protocol):
    """
    Protocol for the route-facing Generation service.

    This keeps the API layer decoupled from the concrete orchestration wiring.
    """

    def start_generation(
        self,
        request: GenerationJobRequest,
    ) -> GenerationOrchestratorResponse:
        """
        Start one Generation job and return the orchestration response.
        """
        ...

    def get_status(self, job_id: str) -> GenerationJobResponse | None:
        """
        Return the latest job status for a Generation job, or None if missing.
        """
        ...


# ------------------------------------------------------------------------------
# Dependency hooks
# ------------------------------------------------------------------------------


def get_generation_route_service() -> GenerationRouteService:
    """
    Route dependency placeholder.

    Override this in application wiring / tests with the concrete service.
    """
    raise NotImplementedError(
        "get_generation_route_service must be overridden with a concrete GenerationRouteService."
    )


def get_sse_publisher() -> SSEPublisher:
    """
    Route dependency placeholder.

    Override this in application wiring / tests with the concrete SSEPublisher.
    """
    raise NotImplementedError(
        "get_sse_publisher must be overridden with a concrete SSEPublisher."
    )


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------


@router.post(
    "/api/generate-document",
    response_model=GenerationOrchestratorResponse,
)
def generate_document(
    request: GenerationJobRequest,
    generation_service: GenerationRouteService = Depends(get_generation_route_service),
) -> GenerationOrchestratorResponse:
    """
    Start a Generation job.

    This is the Generation pipeline entry point defined in the aligned plan.
    """
    return generation_service.start_generation(request)


@router.get(
    "/api/generate-document/{job_id}/status",
    response_model=GenerationJobResponse,
)
def get_generation_status(
    job_id: str,
    generation_service: GenerationRouteService = Depends(get_generation_route_service),
) -> GenerationJobResponse:
    """
    Return the latest known status for one Generation job.
    """
    result = generation_service.get_status(job_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Generation job '{job_id}' not found.")
    return result


@router.get("/api/generate-document/{job_id}/events")
async def stream_generation_events(
    job_id: str,
    last_sequence_id: int | None = Query(
        default=None,
        ge=0,
        description="Replay events with sequence_id greater than this value.",
    ),
    replay_only: bool = Query(
        default=False,
        description="If true, return currently available events and close the stream.",
    ),
    max_events: int | None = Query(
        default=None,
        ge=1,
        description="Optional cap for number of events emitted before closing the stream.",
    ),
    poll_interval_ms: int = Query(
        default=250,
        ge=50,
        le=10_000,
        description="Polling interval used for SSE replay/live event checks.",
    ),
    sse_publisher: SSEPublisher = Depends(get_sse_publisher),
) -> StreamingResponse:
    """
    Stream Generation progress events via SSE.

    Notes:
    - `replay_only=true` is useful for tests or one-shot event retrieval.
    - default behavior keeps polling for new events and streaming them live.
    """

    async def event_stream() -> AsyncIterator[str]:
        emitted = 0
        current_sequence_id = last_sequence_id

        while True:
            events = sse_publisher.get_events_since(
                sequence_id=current_sequence_id,
                job_id=job_id,
            )

            if events:
                for event in events:
                    yield sse_publisher.to_sse_payload(event)
                    current_sequence_id = event.sequence_id
                    emitted += 1

                    if max_events is not None and emitted >= max_events:
                        return

                if replay_only:
                    return
            else:
                if replay_only:
                    return

            await asyncio.sleep(poll_interval_ms / 1000.0)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )