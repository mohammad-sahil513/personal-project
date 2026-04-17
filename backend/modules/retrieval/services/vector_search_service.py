# backend/modules/retrieval/services/vector_search_service.py

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.retrieval.contracts.retrieval_contracts import (
    PoolName,
    RetrievalFilters,
    RetrievalPlan,
    RetrievalWarningCode,
)

from backend.modules.retrieval.repositories.search_repository import SearchCandidate
from backend.modules.retrieval.services.query_builder import QueryBuildResult


MIN_SECTION_DISCOVERY_COUNT = 3
MIN_SUMMARY_COVERAGE_RATIO = 0.50


class SearchRepositoryProtocol(Protocol):
    def search_section_discovery(
        self,
        *,
        pool: PoolName,
        query: QueryBuildResult,
        plan: RetrievalPlan,
        filters: RetrievalFilters | None = None,
        top_sections: int = MIN_SECTION_DISCOVERY_COUNT,
    ) -> list[SearchCandidate]:
        ...

    def search_chunks_by_section_ids(
        self,
        *,
        pool: PoolName,
        query: QueryBuildResult,
        plan: RetrievalPlan,
        section_ids: list[str],
        filters: RetrievalFilters | None = None,
    ) -> list[SearchCandidate]:
        ...

    def flat_search(
        self,
        *,
        pool: PoolName,
        query: QueryBuildResult,
        plan: RetrievalPlan,
        filters: RetrievalFilters | None = None,
    ) -> list[SearchCandidate]:
        ...


class PoolSearchResult(BaseModel):
    """
    Hierarchical retrieval result for one pool.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    pool: PoolName
    strategy_used: str = Field(
        ...,
        description="hierarchical | flat_fallback | legacy_section_type_fallback",
    )
    selected_section_ids: list[str] = Field(default_factory=list)
    section_discovery_count: int = Field(default=0, ge=0)
    summary_coverage_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    candidates: list[SearchCandidate] = Field(default_factory=list)
    used_flat_fallback: bool = False
    legacy_section_type_fallback_used: bool = False
    warnings: list[RetrievalWarningCode] = Field(default_factory=list)


class HierarchicalSearchResult(BaseModel):
    """
    Combined retrieval execution result across active pools.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    source: PoolSearchResult | None = None
    guideline: PoolSearchResult | None = None
    warnings: list[RetrievalWarningCode] = Field(default_factory=list)


class VectorSearchService:
    """
    Implements the locked hierarchical retrieval mechanics:

    1. section discovery (summary-backed)
    2. chunk retrieval restricted by section_id
    3. flat fallback if:
       - fewer than 3 usable section_ids are found, or
       - summary coverage is < 50%, or
       - section_id is unavailable for legacy data
    """

    def __init__(
        self,
        search_repository: SearchRepositoryProtocol,
        *,
        min_section_discovery_count: int = MIN_SECTION_DISCOVERY_COUNT,
        min_summary_coverage_ratio: float = MIN_SUMMARY_COVERAGE_RATIO,
    ) -> None:
        self._search_repository = search_repository
        self._min_section_discovery_count = min_section_discovery_count
        self._min_summary_coverage_ratio = min_summary_coverage_ratio

    def search(
        self,
        *,
        query: QueryBuildResult,
        plan: RetrievalPlan,
        filters: RetrievalFilters | None = None,
    ) -> HierarchicalSearchResult:
        """
        Execute hierarchical retrieval for all enabled pools.
        """
        source_result = None
        guideline_result = None
        warnings: list[str] = []

        effective_filters = filters or plan.filters

        if plan.source_enabled:
            source_result = self.search_pool(
                pool=PoolName.SOURCE,
                query=query,
                plan=plan,
                filters=effective_filters,
            )
            warnings.extend(source_result.warnings)

        if plan.guideline_enabled:
            guideline_result = self.search_pool(
                pool=PoolName.GUIDELINE,
                query=query,
                plan=plan,
                filters=effective_filters,
            )
            warnings.extend(guideline_result.warnings)

        return HierarchicalSearchResult(
            source=source_result,
            guideline=guideline_result,
            warnings=warnings,
        )

    def search_pool(
        self,
        *,
        pool: PoolName,
        query: QueryBuildResult,
        plan: RetrievalPlan,
        filters: RetrievalFilters | None = None,
    ) -> PoolSearchResult:
        """
        Execute hierarchical retrieval for a single pool.
        """
        effective_filters = filters or plan.filters
        warnings: list[str] = []

        # Pass 1 — summary-backed section discovery
        discovery_candidates = self._search_repository.search_section_discovery(
            pool=pool,
            query=query,
            plan=plan,
            filters=effective_filters,
            top_sections=self._min_section_discovery_count,
        )

        usable_section_ids = self._extract_section_ids(discovery_candidates)
        summary_coverage_ratio = self._compute_summary_coverage_ratio(discovery_candidates)

        # Legacy fallback if section_id is unavailable in retrieved candidates
        if self._section_ids_unavailable(discovery_candidates):
            warnings.append(RetrievalWarningCode.LEGACY_SECTION_TYPE_FALLBACK)
            fallback_candidates = self._search_repository.flat_search(
                pool=pool,
                query=query,
                plan=plan,
                filters=effective_filters,
            )
            return PoolSearchResult(
                pool=pool,
                strategy_used="legacy_section_type_fallback",
                selected_section_ids=[],
                section_discovery_count=0,
                summary_coverage_ratio=summary_coverage_ratio,
                candidates=fallback_candidates,
                used_flat_fallback=True,
                legacy_section_type_fallback_used=True,
                warnings=warnings,
            )

        # Flat fallback if too few section IDs
        if len(usable_section_ids) < self._min_section_discovery_count:
            warnings.append(RetrievalWarningCode.TOO_FEW_SECTION_IDS)
            if len(usable_section_ids) == 0:
                warnings.append(RetrievalWarningCode.EMPTY_RESULTS)
            fallback_candidates = self._search_repository.flat_search(
                pool=pool,
                query=query,
                plan=plan,
                filters=effective_filters,
            )
            return PoolSearchResult(
                pool=pool,
                strategy_used="flat_fallback",
                selected_section_ids=usable_section_ids,
                section_discovery_count=len(usable_section_ids),
                summary_coverage_ratio=summary_coverage_ratio,
                candidates=fallback_candidates,
                used_flat_fallback=True,
                legacy_section_type_fallback_used=False,
                warnings=warnings,
            )

        # Flat fallback if summary coverage is too low
        if summary_coverage_ratio < self._min_summary_coverage_ratio:
            warnings.append(RetrievalWarningCode.LOW_SUMMARY_COVERAGE)
            fallback_candidates = self._search_repository.flat_search(
                pool=pool,
                query=query,
                plan=plan,
                filters=effective_filters,
            )
            return PoolSearchResult(
                pool=pool,
                strategy_used="flat_fallback",
                selected_section_ids=usable_section_ids,
                section_discovery_count=len(usable_section_ids),
                summary_coverage_ratio=summary_coverage_ratio,
                candidates=fallback_candidates,
                used_flat_fallback=True,
                legacy_section_type_fallback_used=False,
                warnings=warnings,
            )

        # Pass 2 — retrieve chunks restricted to selected section_ids
        chunk_candidates = self._search_repository.search_chunks_by_section_ids(
            pool=pool,
            query=query,
            plan=plan,
            section_ids=usable_section_ids,
            filters=effective_filters,
        )

        return PoolSearchResult(
            pool=pool,
            strategy_used="hierarchical",
            selected_section_ids=usable_section_ids,
            section_discovery_count=len(usable_section_ids),
            summary_coverage_ratio=summary_coverage_ratio,
            candidates=chunk_candidates,
            used_flat_fallback=False,
            legacy_section_type_fallback_used=False,
            warnings=warnings,
        )

    @staticmethod
    def _extract_section_ids(candidates: list[SearchCandidate]) -> list[str]:
        """
        Extract distinct, non-empty section_ids in stable order.
        """
        seen: set[str] = set()
        ordered: list[str] = []

        for candidate in candidates:
            section_id = getattr(candidate.document, "section_id", None)
            if not isinstance(section_id, str):
                continue
            section_id = section_id.strip()
            if not section_id:
                continue
            if section_id not in seen:
                seen.add(section_id)
                ordered.append(section_id)

        return ordered

    @staticmethod
    def _compute_summary_coverage_ratio(candidates: list[SearchCandidate]) -> float:
        """
        Compute ratio of candidates that have non-empty summary support.
        """
        if not candidates:
            return 0.0

        with_summary = 0
        for candidate in candidates:
            summary = getattr(candidate.document, "summary", None)
            if isinstance(summary, str) and summary.strip():
                with_summary += 1

        return with_summary / len(candidates)

    @staticmethod
    def _section_ids_unavailable(candidates: list[SearchCandidate]) -> bool:
        """
        Detect legacy data where section_id is missing/blank in discovered candidates.
        """
        if not candidates:
            return False

        for candidate in candidates:
            section_id = getattr(candidate.document, "section_id", None)
            if not isinstance(section_id, str):
                return True
            if not section_id.strip():
                return True

        return False