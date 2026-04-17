from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.modules.ingestion.observability.models import IngestionRunContext
from backend.modules.ingestion.observability.observer import IngestionObserverProtocol


class ObservedStageRunner:
    """
    Thin wrapper around an existing stage runner.

    This lets us add observability with minimal change:
    - no business logic rewrite
    - no changes to the existing stage implementations
    """

    def __init__(
        self,
        *,
        stage_name: str,
        inner_runner: Any,
        observer: IngestionObserverProtocol,
        safe_metadata_builder,
        context: IngestionRunContext,
    ) -> None:
        self._stage_name = stage_name
        self._inner_runner = inner_runner
        self._observer = observer
        self._safe_metadata_builder = safe_metadata_builder
        self._context = context

    async def run(self, request: Any) -> Any:
        started_at = datetime.now(UTC)
        safe_metadata = self._safe_metadata_builder(self._stage_name, request)

        self._observer.on_stage_started(
            context=self._context,
            stage_name=self._stage_name,
            safe_metadata=safe_metadata,
        )

        try:
            result = await self._inner_runner.run(request)
        except Exception as exc:
            self._observer.on_stage_failed(
                context=self._context,
                stage_name=self._stage_name,
                started_at=started_at,
                error=exc,
                safe_metadata=safe_metadata,
            )
            raise

        self._observer.on_stage_completed(
            context=self._context,
            stage_name=self._stage_name,
            started_at=started_at,
            output_model=result,
            safe_metadata=safe_metadata,
        )
        return result


def default_safe_metadata_builder(stage_name: str, request: Any) -> dict[str, Any]:
    """
    Build safe metadata without logging request body/content.

    This function intentionally logs *only metadata* that is safe to expose in files.
    """
    metadata: dict[str, Any] = {
        "stage_name": stage_name,
    }

    for field_name in ("process_id", "document_id", "file_name", "content_type", "index_name", "max_vision_calls"):
        value = getattr(request, field_name, None)
        if value is not None:
            metadata[field_name] = value

    # Add count-like metadata only where it helps demo understanding.
    for list_field_name in ("chunks", "sections"):
        value = getattr(request, list_field_name, None)
        if isinstance(value, list):
            metadata[f"{list_field_name}_count"] = len(value)

    file_bytes = getattr(request, "file_bytes", None)
    if isinstance(file_bytes, (bytes, bytearray)):
        metadata["file_size_bytes"] = len(file_bytes)

    return metadata