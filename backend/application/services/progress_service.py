"""
Application service for workflow progress handling.
"""

from __future__ import annotations

from typing import Any

from backend.pipeline.planners.progress_planner import (
    PHASE_STATUS_COMPLETED,
    PHASE_STATUS_FAILED,
    PHASE_STATUS_NOT_STARTED,
    PHASE_STATUS_RUNNING,
    build_default_phase_states,
    calculate_overall_progress,
    get_current_phase,
    get_phase_state,
    update_phase_state,
)


class ProgressService:
    """
    Backend use-case service for workflow progress initialization and updates.
    """

    def initialize_progress(self) -> dict[str, Any]:
        phases = build_default_phase_states()

        return {
            "current_phase": get_current_phase(phases),
            "overall_progress_percent": calculate_overall_progress(phases),
            "phases": phases,
        }

    def mark_phase_running(
        self,
        phases: list[dict[str, Any]],
        phase_name: str,
        progress_percent: int = 0,
    ) -> dict[str, Any]:
        updated_phases = update_phase_state(
            phases,
            phase_name=phase_name,
            status=PHASE_STATUS_RUNNING,
            progress_percent=progress_percent,
        )

        return self._build_progress_snapshot(updated_phases)

    def update_phase_progress(
        self,
        phases: list[dict[str, Any]],
        phase_name: str,
        progress_percent: int,
    ) -> dict[str, Any]:
        current = get_phase_state(phases, phase_name)

        status = current["status"]
        if status == PHASE_STATUS_NOT_STARTED:
            status = PHASE_STATUS_RUNNING

        updated_phases = update_phase_state(
            phases,
            phase_name=phase_name,
            status=status,
            progress_percent=progress_percent,
        )

        return self._build_progress_snapshot(updated_phases)

    def mark_phase_completed(
        self,
        phases: list[dict[str, Any]],
        phase_name: str,
    ) -> dict[str, Any]:
        updated_phases = update_phase_state(
            phases,
            phase_name=phase_name,
            status=PHASE_STATUS_COMPLETED,
            progress_percent=100,
        )

        return self._build_progress_snapshot(updated_phases)

    def mark_phase_failed(
        self,
        phases: list[dict[str, Any]],
        phase_name: str,
        progress_percent: int | None = None,
    ) -> dict[str, Any]:
        updated_phases = update_phase_state(
            phases,
            phase_name=phase_name,
            status=PHASE_STATUS_FAILED,
            progress_percent=progress_percent,
        )

        return self._build_progress_snapshot(updated_phases)

    def _build_progress_snapshot(self, phases: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "current_phase": get_current_phase(phases),
            "overall_progress_percent": calculate_overall_progress(phases),
            "phases": phases,
        }