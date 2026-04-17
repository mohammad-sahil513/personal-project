"""
Application service for building frontend-friendly ingestion status payloads.
"""

from __future__ import annotations

from typing import Any

from backend.application.dto.ingestion_dto import IngestionExecutionDTO


INGESTION_STAGE_LABELS: dict[str, str] = {
    "01_UPLOAD_AND_DEDUP": "Upload and deduplication",
    "02_PARSE_DOCUMENT": "Parse document",
    "03_MASK_PII": "Mask PII",
    "04_CLASSIFY_IMAGES": "Classify images",
    "05_VISION_EXTRACTION": "Vision extraction",
    "06_SEGMENT_SECTIONS": "Segment sections",
    "07_VALIDATE_OUTPUTS": "Validate outputs",
    "08_SEMANTIC_CHUNKING": "Semantic chunking",
    "09_VECTOR_INDEXING": "Vector indexing",
}


class IngestionStatusService:
    """
    Build frontend-friendly ingestion status summaries from ingestion execution DTOs.
    """

    def build_status_block(self, ingestion_execution: IngestionExecutionDTO) -> dict[str, Any]:
        progress_percent = self._calculate_progress_percent(
            completed_stages=ingestion_execution.completed_stages,
            total_stages=ingestion_execution.total_stages,
            status=ingestion_execution.status,
        )

        current_stage_label = INGESTION_STAGE_LABELS.get(
            ingestion_execution.current_stage,
            ingestion_execution.current_stage,
        )

        has_duplicate_warning = any(
            item.get("code") == "INGESTION_DUPLICATE_SKIPPED"
            for item in (ingestion_execution.warnings or [])
        )

        has_validation_error = any(
            item.get("code") in {"VALIDATION_BLOCKED", "INGESTION_FAILED"}
            for item in (ingestion_execution.errors or [])
        )

        terminal_hint = self._build_terminal_hint(
            ingestion_execution=ingestion_execution,
            has_duplicate_warning=has_duplicate_warning,
            has_validation_error=has_validation_error,
        )

        return {
            "execution_id": ingestion_execution.execution_id,
            "status": ingestion_execution.status,
            "current_stage": ingestion_execution.current_stage,
            "current_stage_label": current_stage_label,
            "completed_stages": ingestion_execution.completed_stages,
            "total_stages": ingestion_execution.total_stages,
            "progress_percent": progress_percent,
            "warnings_count": len(ingestion_execution.warnings or []),
            "errors_count": len(ingestion_execution.errors or []),
            "artifact_count": len(ingestion_execution.artifacts or []),
            "has_duplicate_warning": has_duplicate_warning,
            "has_validation_error": has_validation_error,
            "terminal_hint": terminal_hint,
            "warnings": ingestion_execution.warnings,
            "errors": ingestion_execution.errors,
            "artifacts": ingestion_execution.artifacts,
        }

    def build_step_label(self, ingestion_execution: IngestionExecutionDTO) -> str:
        current_stage_label = INGESTION_STAGE_LABELS.get(
            ingestion_execution.current_stage,
            ingestion_execution.current_stage,
        )

        if ingestion_execution.status == "FAILED":
            return f"Ingestion failed at: {current_stage_label}"

        if ingestion_execution.status == "COMPLETED":
            return "Ingestion completed"

        return f"Ingestion: {current_stage_label}"

    def _calculate_progress_percent(
        self,
        *,
        completed_stages: int,
        total_stages: int,
        status: str,
    ) -> int:
        if total_stages <= 0:
            return 0

        if status == "COMPLETED":
            return 100

        return int(round((completed_stages / total_stages) * 100))

    def _build_terminal_hint(
        self,
        *,
        ingestion_execution: IngestionExecutionDTO,
        has_duplicate_warning: bool,
        has_validation_error: bool,
    ) -> str | None:
        if ingestion_execution.status == "COMPLETED" and has_duplicate_warning:
            return "Ingestion completed through duplicate short-circuit"

        if ingestion_execution.status == "FAILED" and has_validation_error:
            return "Ingestion failed due to validation/runtime issue"

        if ingestion_execution.status == "COMPLETED":
            return "Ingestion completed successfully"

        return None