"""
Shared cost aggregation service for the observability module.

Responsibilities:
- Accumulate estimated cost entries
- Aggregate by section, category, and job/document
- Return summary totals for downstream observability/reporting

Important:
- This file is aggregation-only.
- It does NOT estimate cost.
- It does NOT emit logs.
- It is intentionally in-memory and DB-free for the current phase.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.observability.services.cost_estimator_service import CostEstimate


class CostRecord(BaseModel):
    """
    One recorded cost event tied to a job and optionally a section.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(description="Stable Generation job/document identifier.")
    category: str = Field(description="Logical cost category, e.g. generation_section.")
    estimate: CostEstimate = Field(description="The estimated cost payload.")
    section_id: str | None = Field(
        default=None,
        description="Optional section identifier for section-scoped cost records.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata for downstream reporting/debugging.",
    )


class CostSummary(BaseModel):
    """
    Aggregated cost summary for one job/document.
    """

    model_config = ConfigDict(extra="forbid")

    job_id: str = Field(description="Stable job/document identifier.")
    total_amount: float = Field(ge=0, description="Total aggregated estimated cost.")
    currency: str = Field(default="USD", description="Currency used by aggregated costs.")
    record_count: int = Field(ge=0, description="Number of aggregated cost records.")
    by_category: dict[str, float] = Field(
        default_factory=dict,
        description="Aggregated cost totals by logical category.",
    )
    by_section: dict[str, float] = Field(
        default_factory=dict,
        description="Aggregated cost totals by section_id.",
    )


class CostAggregationService:
    """
    In-memory cost aggregation service.

    Usage:
    - add one cost record at a time
    - query section totals / category totals / full job summary
    - clear one job or all state when needed
    """

    def __init__(self) -> None:
        self._records_by_job: dict[str, list[CostRecord]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_cost_record(
        self,
        *,
        job_id: str,
        category: str,
        estimate: CostEstimate,
        section_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CostRecord:
        """
        Add one estimated cost record to the aggregation store.
        """
        if not job_id or not job_id.strip():
            raise ValueError("job_id cannot be empty.")
        if not category or not category.strip():
            raise ValueError("category cannot be empty.")

        record = CostRecord(
            job_id=job_id,
            category=category,
            estimate=estimate,
            section_id=section_id,
            metadata=metadata or {},
        )
        self._records_by_job[job_id].append(record)
        return record

    def get_records(self, job_id: str) -> list[CostRecord]:
        """
        Return all recorded cost events for one job.
        """
        if not job_id or not job_id.strip():
            raise ValueError("job_id cannot be empty.")

        return list(self._records_by_job.get(job_id, []))

    def get_total_cost(self, job_id: str) -> float:
        """
        Return the total aggregated amount for one job.
        """
        return round(sum(record.estimate.amount for record in self.get_records(job_id)), 10)

    def get_category_totals(self, job_id: str) -> dict[str, float]:
        """
        Return aggregated totals by category for one job.
        """
        totals: dict[str, float] = defaultdict(float)

        for record in self.get_records(job_id):
            totals[record.category] += record.estimate.amount

        return {key: round(value, 10) for key, value in totals.items()}

    def get_section_totals(self, job_id: str) -> dict[str, float]:
        """
        Return aggregated totals by section_id for one job.

        Records without a section_id are omitted from this view.
        """
        totals: dict[str, float] = defaultdict(float)

        for record in self.get_records(job_id):
            if record.section_id is None:
                continue
            totals[record.section_id] += record.estimate.amount

        return {key: round(value, 10) for key, value in totals.items()}

    def get_summary(self, job_id: str) -> CostSummary:
        """
        Return a full aggregated summary for one job.
        """
        records = self.get_records(job_id)

        currency = "USD"
        if records:
            currencies = {record.estimate.currency for record in records}
            if len(currencies) > 1:
                raise ValueError(
                    f"Multiple currencies detected for job '{job_id}': {sorted(currencies)}"
                )
            currency = next(iter(currencies))

        return CostSummary(
            job_id=job_id,
            total_amount=self.get_total_cost(job_id),
            currency=currency,
            record_count=len(records),
            by_category=self.get_category_totals(job_id),
            by_section=self.get_section_totals(job_id),
        )

    def clear_job(self, job_id: str) -> None:
        """
        Remove all aggregated records for one job.
        """
        if not job_id or not job_id.strip():
            raise ValueError("job_id cannot be empty.")
        self._records_by_job.pop(job_id, None)

    def clear_all(self) -> None:
        """
        Remove all aggregation state.
        """
        self._records_by_job.clear()