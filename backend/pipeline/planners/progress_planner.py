"""
Workflow progress planning helpers.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


WORKFLOW_PHASE_ORDER: list[str] = [
    "INPUT_PREPARATION",
    "INGESTION",
    "TEMPLATE_PREPARATION",
    "SECTION_PLANNING",
    "RETRIEVAL",
    "GENERATION",
    "ASSEMBLY_VALIDATION",
    "RENDER_EXPORT",
]

WORKFLOW_PHASE_WEIGHTS: dict[str, int] = {
    "INPUT_PREPARATION": 5,
    "INGESTION": 35,
    "TEMPLATE_PREPARATION": 10,
    "SECTION_PLANNING": 5,
    "RETRIEVAL": 15,
    "GENERATION": 20,
    "ASSEMBLY_VALIDATION": 5,
    "RENDER_EXPORT": 5,
}

PHASE_STATUS_NOT_STARTED = "NOT_STARTED"
PHASE_STATUS_RUNNING = "RUNNING"
PHASE_STATUS_COMPLETED = "COMPLETED"
PHASE_STATUS_FAILED = "FAILED"
PHASE_STATUS_SKIPPED = "SKIPPED"


def clamp_progress(value: int | float) -> int:
    """
    Clamp progress into the range [0, 100].
    """
    if value < 0:
        return 0
    if value > 100:
        return 100
    return int(value)


def build_default_phase_states() -> list[dict[str, Any]]:
    """
    Build the default workflow phase progress structure.
    """
    return [
        {
            "phase": phase,
            "status": PHASE_STATUS_NOT_STARTED,
            "progress_percent": 0,
            "weight": WORKFLOW_PHASE_WEIGHTS[phase],
        }
        for phase in WORKFLOW_PHASE_ORDER
    ]


def update_phase_state(
    phases: list[dict[str, Any]],
    *,
    phase_name: str,
    status: str | None = None,
    progress_percent: int | None = None,
) -> list[dict[str, Any]]:
    """
    Return a new phase list with a single phase updated.
    """
    updated = deepcopy(phases)

    found = False
    for phase in updated:
        if phase["phase"] == phase_name:
            if status is not None:
                phase["status"] = status
            if progress_percent is not None:
                phase["progress_percent"] = clamp_progress(progress_percent)
            found = True
            break

    if not found:
        raise ValueError(f"Unknown phase: {phase_name}")

    return updated


def get_phase_state(
    phases: list[dict[str, Any]],
    phase_name: str,
) -> dict[str, Any]:
    """
    Fetch a single phase state by name.
    """
    for phase in phases:
        if phase["phase"] == phase_name:
            return phase

    raise ValueError(f"Unknown phase: {phase_name}")


def calculate_overall_progress(phases: list[dict[str, Any]]) -> int:
    """
    Calculate overall workflow progress using weighted phase progress.
    """
    total = 0.0

    for phase in phases:
        weight = phase["weight"]
        progress_percent = clamp_progress(phase["progress_percent"])
        total += weight * (progress_percent / 100.0)

    return clamp_progress(round(total))


def get_current_phase(phases: list[dict[str, Any]]) -> str:
    """
    Return the current phase for display/status purposes.

    Priority:
    1. RUNNING phase
    2. FAILED phase
    3. first NOT_STARTED phase
    4. final phase fallback
    """
    for phase in phases:
        if phase["status"] == PHASE_STATUS_RUNNING:
            return phase["phase"]

    for phase in phases:
        if phase["status"] == PHASE_STATUS_FAILED:
            return phase["phase"]

    for phase in phases:
        if phase["status"] == PHASE_STATUS_NOT_STARTED:
            return phase["phase"]

    return WORKFLOW_PHASE_ORDER[-1]