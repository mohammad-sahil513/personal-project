"""
Unit tests — Phase 4.2 (reranker_service)
RerankerService is a pure deterministic scoring algorithm — no mocks required.
"""

from __future__ import annotations

import pytest

from backend.modules.retrieval.contracts.index_contracts import IndexedChunkDocument
from backend.modules.retrieval.contracts.retrieval_contracts import PoolName, RetrievalPlan
from backend.modules.retrieval.repositories.search_repository import SearchCandidate
from backend.modules.retrieval.services.reranker_service import RerankerService


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _make_candidate(
    chunk_id: str = "chk_001",
    chunk_index: int = 0,
    semantic_score: float | None = 0.80,
    bm25_score: float | None = 5.0,
    pool: PoolName = PoolName.SOURCE,
) -> SearchCandidate:
    doc = IndexedChunkDocument(
        chunk_id=chunk_id,
        document_id="doc_001",
        section_id="sec_overview",
        document_type="SOURCE",
        section_type="OVERVIEW",
        content="Some content.",
        chunk_index_in_section=chunk_index,
    )
    return SearchCandidate(
        document=doc,
        source_role=pool,
        matched_on="content",
        semantic_score=semantic_score,
        bm25_score=bm25_score,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRerankerServiceScoring:
    def test_higher_semantic_score_ranks_first(self):
        low = _make_candidate(chunk_id="low", semantic_score=0.40)
        high = _make_candidate(chunk_id="high", semantic_score=0.90)
        ranked = RerankerService.rerank(
            source_candidates=[low, high],
            guideline_candidates=[],
            plan=RetrievalPlan(),
        )
        assert ranked[0].document.chunk_id == "high"
        assert ranked[1].document.chunk_id == "low"

    def test_zero_semantic_score_candidate_still_returned(self):
        c = _make_candidate(chunk_id="zero_sem", semantic_score=0.0, bm25_score=10.0)
        ranked = RerankerService.rerank(
            source_candidates=[c],
            guideline_candidates=[],
            plan=RetrievalPlan(),
        )
        assert len(ranked) == 1

    def test_none_scores_treated_as_zero(self):
        c = _make_candidate(chunk_id="none_scores", semantic_score=None, bm25_score=None)
        ranked = RerankerService.rerank(
            source_candidates=[c],
            guideline_candidates=[],
            plan=RetrievalPlan(),
        )
        assert len(ranked) == 1
        assert ranked[0].document.chunk_id == "none_scores"


class TestRerankerServiceOrdering:
    def test_source_candidates_precede_guideline(self):
        src = _make_candidate(chunk_id="src_1", semantic_score=0.50, pool=PoolName.SOURCE)
        gl = _make_candidate(chunk_id="gl_1", semantic_score=0.99, pool=PoolName.GUIDELINE)

        # Even though guideline has a higher semantic score, SOURCE pool bias
        # means all SOURCE candidates come before GUIDELINE in the combined list.
        ranked = RerankerService.rerank(
            source_candidates=[src],
            guideline_candidates=[gl],
            plan=RetrievalPlan(),
        )
        source_positions = [i for i, c in enumerate(ranked) if c.source_role == PoolName.SOURCE]
        guideline_positions = [i for i, c in enumerate(ranked) if c.source_role == PoolName.GUIDELINE]
        assert max(source_positions) < min(guideline_positions)

    def test_tie_broken_by_chunk_index(self):
        """Equal scores → smaller chunk_index_in_section comes first."""
        c0 = _make_candidate(chunk_id="chk_0", chunk_index=0, semantic_score=0.75, bm25_score=5.0)
        c1 = _make_candidate(chunk_id="chk_1", chunk_index=1, semantic_score=0.75, bm25_score=5.0)
        ranked = RerankerService.rerank(
            source_candidates=[c1, c0],
            guideline_candidates=[],
            plan=RetrievalPlan(),
        )
        assert ranked[0].document.chunk_id == "chk_0"

    def test_final_output_capped_by_plan(self):
        candidates = [
            _make_candidate(chunk_id=f"chk_{i}", semantic_score=0.9 - i * 0.01)
            for i in range(20)
        ]
        plan = RetrievalPlan(final_output_top_k=5)
        ranked = RerankerService.rerank(
            source_candidates=candidates,
            guideline_candidates=[],
            plan=plan,
        )
        assert len(ranked) == 5

    def test_empty_candidates_returns_empty(self):
        ranked = RerankerService.rerank(
            source_candidates=[],
            guideline_candidates=[],
            plan=RetrievalPlan(),
        )
        assert ranked == []

    def test_bm25_normalization_does_not_crash_with_all_zero_bm25(self):
        """max_bm25=0 → bm25_norm should not cause ZeroDivisionError (uses 1.0 fallback)."""
        c1 = _make_candidate(chunk_id="c1", bm25_score=0.0, semantic_score=0.8)
        c2 = _make_candidate(chunk_id="c2", bm25_score=0.0, semantic_score=0.5)
        ranked = RerankerService.rerank(
            source_candidates=[c1, c2],
            guideline_candidates=[],
            plan=RetrievalPlan(),
        )
        assert ranked[0].document.chunk_id == "c1"   # higher semantic wins
