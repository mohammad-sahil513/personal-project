"""
Wave executor for the Generation module.

Responsibilities:
- Compute dependency waves
- Execute sections in the same wave concurrently
- Respect max_parallel_sections limits
- Return structured wave execution summaries and section responses

Important:
- This file is orchestration-only.
- It does NOT perform Retrieval, prompt assembly, validation, or export itself.
- Section-level execution is delegated to SectionExecutor.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from math import ceil
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.generation.contracts.generation_contracts import (
    GenerationStrategy,
)
from backend.modules.generation.contracts.session_contracts import (
    SectionRuntimeState,
)
from backend.modules.generation.models.generation_config import (
    DEFAULT_GENERATION_CONFIG,
    GenerationConfig,
)
from backend.modules.generation.orchestrators.dependency_checker import (
    DependencyChecker,
)
from backend.modules.generation.orchestrators.section_executor import (
    SectionExecutionRequest,
    SectionExecutionResponse,
    SectionExecutor,
)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class WaveSectionPlan(BaseModel):
    """
    Execution plan for one section inside wave execution.

    This wraps the SectionExecutionRequest with dependency IDs so the wave
    planner can compute execution layers before invoking the SectionExecutor.
    """

    model_config = ConfigDict(extra="forbid")

    request: SectionExecutionRequest = Field(
        description="Section execution request delegated to SectionExecutor."
    )
    dependency_ids: list[str] = Field(
        default_factory=list,
        description="Section IDs that must complete before this section can run.",
    )


class WaveExecutionSummary(BaseModel):
    """
    Summary for one computed execution wave.
    """

    model_config = ConfigDict(extra="forbid")

    wave_index: int = Field(ge=0, description="Zero-based wave index.")
    section_ids: list[str] = Field(
        default_factory=list,
        description="Section IDs that belong to this wave.",
    )
    batches_executed: int = Field(
        default=0,
        ge=0,
        description="How many internal parallel batches were used for this wave.",
    )
    started_at: datetime = Field(description="Wave start timestamp (UTC).")
    completed_at: datetime = Field(description="Wave completion timestamp (UTC).")


class WaveExecutionResponse(BaseModel):
    """
    Final output of the wave executor.
    """

    model_config = ConfigDict(extra="forbid")

    wave_summaries: list[WaveExecutionSummary] = Field(default_factory=list)
    section_responses: list[SectionExecutionResponse] = Field(default_factory=list)


class WaveExecutor:
    """
    Coordinates dependency-wave execution for Generation sections.

    Flow:
    - compute dependency waves from plans
    - execute each wave in order
    - inside a wave, run sections concurrently in bounded batches
    - return wave summaries + section responses
    """

    def __init__(
        self,
        *,
        dependency_checker: DependencyChecker,
        section_executor: SectionExecutor,
        config: GenerationConfig | None = None,
    ) -> None:
        self.dependency_checker = dependency_checker
        self.section_executor = section_executor
        self.config = config or DEFAULT_GENERATION_CONFIG

    def execute(self, plans: list[WaveSectionPlan]) -> WaveExecutionResponse:
        """
        Execute all supplied section plans using dependency-wave scheduling.
        """
        if not plans:
            return WaveExecutionResponse()

        self._validate_unique_section_ids(plans)

        wave_plan = self._compute_waves(plans)

        section_response_map: dict[str, SectionExecutionResponse] = {}
        wave_summaries: list[WaveExecutionSummary] = []

        for wave_index, section_ids in enumerate(wave_plan):
            wave_started_at = utc_now()

            batches = self._chunk_section_ids(
                section_ids,
                chunk_size=self.config.max_parallel_sections,
            )

            for batch in batches:
                batch_responses = self._execute_batch(batch, plans)
                for response in batch_responses:
                    section_response_map[response.result.section_id] = response

            wave_completed_at = utc_now()
            wave_summaries.append(
                WaveExecutionSummary(
                    wave_index=wave_index,
                    section_ids=section_ids,
                    batches_executed=len(batches),
                    started_at=wave_started_at,
                    completed_at=wave_completed_at,
                )
            )

        # Preserve input-plan order in the final response list
        ordered_responses = [
            section_response_map[plan.request.section_id]
            for plan in plans
            if plan.request.section_id in section_response_map
        ]

        return WaveExecutionResponse(
            wave_summaries=wave_summaries,
            section_responses=ordered_responses,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_waves(self, plans: list[WaveSectionPlan]) -> list[list[str]]:
        """
        Convert plans into lightweight runtime states and compute dependency waves.
        """
        runtime_states = [
            SectionRuntimeState(
                section_id=plan.request.section_id,
                section_heading=plan.request.section_heading,
                strategy=plan.request.strategy,
                dependency_ids=plan.dependency_ids,
            )
            for plan in plans
        ]

        return self.dependency_checker.compute_dependency_wave(runtime_states)

    def _execute_batch(
        self,
        section_ids: list[str],
        plans: list[WaveSectionPlan],
    ) -> list[SectionExecutionResponse]:
        """
        Execute one bounded batch of sections concurrently.

        Responses are returned in the same order as section_ids.
        """
        plan_map = {plan.request.section_id: plan for plan in plans}
        requests = [
            plan_map[section_id].request.model_copy(update={"dependencies_satisfied": True})
            for section_id in section_ids
        ]

        if len(requests) == 1:
            return [self.section_executor.execute(requests[0])]

        max_workers = min(len(requests), self.config.max_parallel_sections)

        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(pool.map(self.section_executor.execute, requests))

        return results

    def _chunk_section_ids(
        self,
        section_ids: list[str],
        *,
        chunk_size: int,
    ) -> list[list[str]]:
        """
        Split a wave into bounded batches when wave size exceeds max_parallel_sections.
        """
        if chunk_size < 1:
            raise ValueError("chunk_size must be >= 1.")

        if not section_ids:
            return []

        total_chunks = ceil(len(section_ids) / chunk_size)
        return [
            section_ids[i * chunk_size : (i + 1) * chunk_size]
            for i in range(total_chunks)
        ]

    def _validate_unique_section_ids(self, plans: Iterable[WaveSectionPlan]) -> None:
        """
        Ensure section IDs are unique across the supplied plans.
        """
        seen: set[str] = set()

        for plan in plans:
            section_id = plan.request.section_id
            if section_id in seen:
                raise ValueError(
                    f"Duplicate section_id detected in wave plans: '{section_id}'."
                )
            seen.add(section_id)