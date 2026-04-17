"""
Unit tests — Phase 4.2 (vector_search_service)
All external search calls are mocked at SearchRepositoryProtocol.
"""

from __future__ import annotations

import pytest

from backend.modules.retrieval.contracts.index_contracts import IndexedChunkDocument
from backend.modules.retrieval.contracts.retrieval_contracts import (
    PoolName,
    RetrievalFilters,
    RetrievalPlan,
    RetrievalWarningCode,
    SearchMode,
)
from backend.modules.retrieval.repositories.search_repository import SearchCandidate
from backend.modules.retrieval.services.query_builder import QueryBuildResult
from backend.modules.retrieval.services.vector_search_service import (
    VectorSearchService,
    PoolSearchResult,
)


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _make_doc(
    chunk_id: str = "chk_001",
    section_id: str = "sec_overview",
    summary: str | None = "A useful summary.",
) -> IndexedChunkDocument:
    return IndexedChunkDocument(
        chunk_id=chunk_id,
        document_id="doc_001",
        section_id=section_id,
        document_type="SOURCE",
        section_type="OVERVIEW",
        content="Some relevant content about the system.",
        summary=summary,
        chunk_index_in_section=0,
    )


def _make_candidate(
    chunk_id: str = "chk_001",
    section_id: str = "sec_overview",
    summary: str | None = "A useful summary.",
    pool: PoolName = PoolName.SOURCE,
    semantic_score: float = 0.85,
) -> SearchCandidate:
    return SearchCandidate(
        document=_make_doc(chunk_id=chunk_id, section_id=section_id, summary=summary),
        source_role=pool,
        matched_on="summary",
        semantic_score=semantic_score,
        bm25_score=2.1,
    )


def _make_query() -> QueryBuildResult:
    return QueryBuildResult(
        query_text="architecture components integration",
        token_count=3,
        semantic_role_key="architecture",
        intent_segment="architecture description",
        heading_segment="System Architecture",
        role_terms_used=["architecture"],
        expansion_terms_used=[],
        trimmed_terms=[],
    )


# ---------------------------------------------------------------------------
# Mock repository
# ---------------------------------------------------------------------------

class _MockSearchRepo:
    """Controllable stub for SearchRepositoryProtocol."""

    def __init__(
        self,
        *,
        discovery_results: list[SearchCandidate] | None = None,
        chunk_results: list[SearchCandidate] | None = None,
        flat_results: list[SearchCandidate] | None = None,
    ):
        self._discovery = discovery_results or []
        self._chunks = chunk_results or []
        self._flat = flat_results or []

    def search_section_discovery(self, *, pool, query, plan, filters=None, top_sections=3):
        return self._discovery

    def search_chunks_by_section_ids(self, *, pool, query, plan, section_ids, filters=None):
        return self._chunks

    def flat_search(self, *, pool, query, plan, filters=None):
        return self._flat


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestVectorSearchServiceHierarchical:
    def test_hierarchical_path_normal(self):
        """3+ distinct section_ids with ≥50% summary coverage → hierarchical strategy."""
        discovery = [
            _make_candidate(chunk_id=f"chk_{i:03d}", section_id=f"sec_{i}", summary="Good summary.")
            for i in range(3)
        ]
        chunks = [_make_candidate(chunk_id="chk_final")]
        repo = _MockSearchRepo(discovery_results=discovery, chunk_results=chunks)
        svc = VectorSearchService(repo)

        result = svc.search_pool(
            pool=PoolName.SOURCE,
            query=_make_query(),
            plan=RetrievalPlan(),
        )

        assert result.strategy_used == "hierarchical"
        assert result.used_flat_fallback is False
        assert result.candidates == chunks

    def test_flat_fallback_when_too_few_section_ids(self):
        """< 3 unique section_ids triggers flat fallback with TOO_FEW_SECTION_IDS warning."""
        discovery = [
            _make_candidate(chunk_id="chk_001", section_id="sec_only_one")
        ]
        flat = [_make_candidate(chunk_id="chk_flat")]
        repo = _MockSearchRepo(discovery_results=discovery, flat_results=flat)
        svc = VectorSearchService(repo)

        result = svc.search_pool(
            pool=PoolName.SOURCE,
            query=_make_query(),
            plan=RetrievalPlan(),
        )

        assert result.strategy_used == "flat_fallback"
        assert result.used_flat_fallback is True
        assert RetrievalWarningCode.TOO_FEW_SECTION_IDS in result.warnings
        assert result.candidates == flat

    def test_empty_discovery_triggers_empty_results_warning(self):
        """Zero candidates from discovery emits EMPTY_RESULTS."""
        repo = _MockSearchRepo(discovery_results=[], flat_results=[])
        svc = VectorSearchService(repo)

        result = svc.search_pool(
            pool=PoolName.SOURCE,
            query=_make_query(),
            plan=RetrievalPlan(),
        )

        assert RetrievalWarningCode.EMPTY_RESULTS in result.warnings

    def test_low_summary_coverage_triggers_flat_fallback(self):
        """< 50% summary coverage → flat fallback with LOW_SUMMARY_COVERAGE."""
        # 3 candidates but none have summary → coverage == 0
        discovery = [
            _make_candidate(chunk_id=f"chk_{i}", section_id=f"sec_{i}", summary=None)
            for i in range(3)
        ]
        flat = [_make_candidate(chunk_id="chk_flat")]
        repo = _MockSearchRepo(discovery_results=discovery, flat_results=flat)
        svc = VectorSearchService(repo, min_summary_coverage_ratio=0.50)

        result = svc.search_pool(
            pool=PoolName.SOURCE,
            query=_make_query(),
            plan=RetrievalPlan(),
        )

        assert result.strategy_used == "flat_fallback"
        assert RetrievalWarningCode.LOW_SUMMARY_COVERAGE in result.warnings

    def test_legacy_fallback_when_section_ids_blank(self):
        """
        Candidates where the document object has a blank/missing section_id
        (as returned by a legacy search client) trigger the legacy fallback path.

        IndexedChunkDocument enforces non-blank section_id at construction, so we
        simulate this by constructing the SearchCandidate via model_construct() to
        bypass validation — matching what SearchRepository does when the raw
        Azure AI Search response contains an empty string.
        """
        # Build a doc with a non-blank section_id first, then patch it to blank
        # using model_construct to mimic raw search-client output.
        doc = _make_doc(chunk_id="chk_legacy_blank", section_id="placeholder", summary="s.")
        # Use model_construct to create a version of the doc with a blank section_id
        patched_doc = IndexedChunkDocument.model_construct(
            **{**doc.model_dump(), "section_id": ""}
        )
        candidate = SearchCandidate.model_construct(
            document=patched_doc,
            source_role=PoolName.SOURCE,
            matched_on="summary",
            semantic_score=0.75,
            bm25_score=3.0,
            raw_payload={},
        )
        flat = [_make_candidate(chunk_id="chk_flat_result")]
        repo = _MockSearchRepo(discovery_results=[candidate], flat_results=flat)
        svc = VectorSearchService(repo)

        result = svc.search_pool(
            pool=PoolName.SOURCE,
            query=_make_query(),
            plan=RetrievalPlan(),
        )

        assert result.strategy_used == "legacy_section_type_fallback"
        assert result.legacy_section_type_fallback_used is True
        assert RetrievalWarningCode.LEGACY_SECTION_TYPE_FALLBACK in result.warnings


class TestVectorSearchServiceFullSearch:
    def test_both_pools_searched(self):
        discovery = [
            _make_candidate(chunk_id=f"chk_{i}", section_id=f"sec_{i}", summary="Summary.")
            for i in range(3)
        ]
        repo = _MockSearchRepo(
            discovery_results=discovery,
            chunk_results=[_make_candidate(chunk_id="chk_src")],
            flat_results=[_make_candidate(chunk_id="chk_gl", pool=PoolName.GUIDELINE)],
        )
        svc = VectorSearchService(repo)
        plan = RetrievalPlan(source_enabled=True, guideline_enabled=True)

        result = svc.search(query=_make_query(), plan=plan)

        assert result.source is not None
        assert result.guideline is not None

    def test_source_only_search(self):
        repo = _MockSearchRepo(
            discovery_results=[
                _make_candidate(chunk_id=f"chk_{i}", section_id=f"sec_{i}", summary="s.")
                for i in range(3)
            ],
            chunk_results=[_make_candidate()],
        )
        svc = VectorSearchService(repo)
        plan = RetrievalPlan(source_enabled=True, guideline_enabled=False)

        result = svc.search(query=_make_query(), plan=plan)

        assert result.source is not None
        assert result.guideline is None
