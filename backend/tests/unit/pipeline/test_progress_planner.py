"""
Unit tests — Phase 7.1 (Pipeline Planners: progress planner)
Covers progress planning helpers.
"""

from __future__ import annotations

import pytest

from backend.pipeline.planners.progress_planner import (
    PHASE_STATUS_COMPLETED,
    PHASE_STATUS_FAILED,
    PHASE_STATUS_NOT_STARTED,
    PHASE_STATUS_RUNNING,
    WORKFLOW_PHASE_ORDER,
    build_default_phase_states,
    calculate_overall_progress,
    clamp_progress,
    get_current_phase,
    get_phase_state,
    update_phase_state,
)


class TestProgressPlanner:
    def test_clamp_progress(self):
        assert clamp_progress(50) == 50
        assert clamp_progress(-10) == 0
        assert clamp_progress(150) == 100
        assert clamp_progress(50.6) == 50

    def test_build_default_phase_states(self):
        phases = build_default_phase_states()
        assert len(phases) == len(WORKFLOW_PHASE_ORDER)
        for phase in phases:
            assert phase["status"] == PHASE_STATUS_NOT_STARTED
            assert phase["progress_percent"] == 0
            assert phase["weight"] > 0

    def test_update_phase_state(self):
        phases = build_default_phase_states()
        updated = update_phase_state(
            phases,
            phase_name="INGESTION",
            status=PHASE_STATUS_RUNNING,
            progress_percent=50,
        )

        old_state = get_phase_state(phases, "INGESTION")
        new_state = get_phase_state(updated, "INGESTION")

        # Ensure immutability
        assert old_state["status"] == PHASE_STATUS_NOT_STARTED
        assert new_state["status"] == PHASE_STATUS_RUNNING
        assert new_state["progress_percent"] == 50

    def test_update_phase_state_unknown_raises(self):
        phases = build_default_phase_states()
        with pytest.raises(ValueError, match="Unknown phase"):
            update_phase_state(phases, phase_name="UNKNOWN_PHASE", status=PHASE_STATUS_COMPLETED)

    def test_get_phase_state_unknown_raises(self):
        phases = build_default_phase_states()
        with pytest.raises(ValueError, match="Unknown phase"):
            get_phase_state(phases, "UNKNOWN_PHASE")

    def test_calculate_overall_progress(self):
        phases = build_default_phase_states()
        assert calculate_overall_progress(phases) == 0

        # Mark first 2 phases as 100% complete
        phases = update_phase_state(phases, phase_name="INPUT_PREPARATION", progress_percent=100)
        phases = update_phase_state(phases, phase_name="INGESTION", progress_percent=100)
        
        # input_prep = 5 weight, ingestion = 35 weight. 40 total
        progress = calculate_overall_progress(phases)
        assert progress == 40
        
        # Complete everything
        for phase_name in WORKFLOW_PHASE_ORDER:
            phases = update_phase_state(phases, phase_name=phase_name, progress_percent=100)
            
        assert calculate_overall_progress(phases) == 100

    def test_get_current_phase(self):
        phases = build_default_phase_states()
        
        # 1. Fallback to first NOT_STARTED
        assert get_current_phase(phases) == "INPUT_PREPARATION"
        
        # 2. Prefer RUNNING over NOT_STARTED
        phases = update_phase_state(phases, phase_name="INGESTION", status=PHASE_STATUS_RUNNING)
        assert get_current_phase(phases) == "INGESTION"
        
        # 3. Prefer RUNNING over FAILED
        phases = update_phase_state(phases, phase_name="TEMPLATE_PREPARATION", status=PHASE_STATUS_FAILED)
        assert get_current_phase(phases) == "INGESTION" # RUNNING has higher priority than FAILED
