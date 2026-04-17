# backend/modules/retrieval/services/reranker_service.py

from __future__ import annotations
from typing import Iterable

from backend.modules.retrieval.contracts.retrieval_contracts import PoolName, RetrievalPlan
from backend.modules.retrieval.repositories.search_repository import SearchCandidate


class RerankerService:
    """
    Normalize scores and enforce SOURCE-first ordering.
    """

    SEM_WEIGHT = 0.45
    BM25_WEIGHT = 0.30
    SECTION_MATCH_WEIGHT = 0.15
    SOURCE_PRIORITY_WEIGHT = 0.10

    @classmethod
    def rerank(
        cls,
        *,
        source_candidates: list[SearchCandidate],
        guideline_candidates: list[SearchCandidate],
        plan: RetrievalPlan,
    ) -> list[SearchCandidate]:
        ranked_source = cls._rerank_pool(source_candidates, PoolName.SOURCE)
        ranked_guideline = cls._rerank_pool(guideline_candidates, PoolName.GUIDELINE)

        # SOURCE-first structural rule
        combined = ranked_source + ranked_guideline

        # Final cap after packaging
        return combined[: plan.final_output_top_k]

    @classmethod
    def _rerank_pool(
        cls,
        candidates: list[SearchCandidate],
        pool: PoolName,
    ) -> list[SearchCandidate]:
        if not candidates:
            return []

        max_bm25 = max((c.bm25_score or 0.0) for c in candidates) or 1.0

        scored: list[tuple[float, int, SearchCandidate]] = []
        for idx, c in enumerate(candidates):
            sem = c.semantic_score or 0.0
            bm25_norm = (c.bm25_score or 0.0) / max_bm25
            section_match = 1.0 if c.document.section_id else 0.0
            source_priority = 1.0 if pool == PoolName.SOURCE else 0.0

            final = (
                cls.SEM_WEIGHT * sem
                + cls.BM25_WEIGHT * bm25_norm
                + cls.SECTION_MATCH_WEIGHT * section_match
                + cls.SOURCE_PRIORITY_WEIGHT * source_priority
            )

            tie_break = c.document.chunk_index_in_section
            scored.append((final, tie_break, c))

        # Sort by score desc, then chunk order asc, then stable index
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [c for _, _, c in scored]