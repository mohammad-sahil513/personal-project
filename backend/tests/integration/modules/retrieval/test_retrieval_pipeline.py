"""
Integration test — Phase 4 Retrieval Module.
Chains: query_builder → vector_search_service → reranker → evidence_packager
        orchestrated by retrieval_service using an in-memory SearchRepository mock.
"""

from __future__ import annotations

import pytest

from backend.modules.retrieval.contracts.evidence_contracts import EvidenceBundle
from backend.modules.retrieval.contracts.index_contracts import IndexedChunkDocument
from backend.modules.retrieval.contracts.retrieval_contracts import (
    FallbackPolicy,
    PoolName,
    RetrievalDiagnostics,
    RetrievalFilters,
    RetrievalPlan,
    RetrievalRequest,
    RetrievalStatus,
    RetrievalWarningCode,
    SearchMode,
)
from backend.modules.retrieval.repositories.search_repository import SearchCandidate
from backend.modules.retrieval.services.retrieval_service import RetrievalService
from backend.modules.retrieval.services.vector_search_service import VectorSearchService


# ---------------------------------------------------------------------------
# In-memory SearchRepository mock
# ---------------------------------------------------------------------------

_TABLE_CONTENT = """\
| Stage | Responsibility |
|-------|----------------|
| 1     | Upload         |
| 2     | Parse          |
"""

_CANDIDATE_STORE: dict[str, list[dict]] = {
    "SOURCE": [
        {
            "chunk_id": "src_chk_001",
            "document_id": "doc_pdd_001",
            "section_id": "sec_overview",
            "document_type": "SOURCE",
            "section_type": "OVERVIEW",
            "content": "The AI SDLC Engine automates document generation for enterprise SDLC workflows.",
            "summary": "AI SDLC Engine product overview and goals.",
            "chunk_index_in_section": 0,
            "has_table": False,
            "has_list": False,
            "has_requirement_id": False,
            "requirement_ids": [],
            "semantic_score": 0.92,
            "bm25_score": 6.5,
        },
        {
            "chunk_id": "src_chk_002",
            "document_id": "doc_pdd_001",
            "section_id": "sec_requirements",
            "document_type": "SOURCE",
            "section_type": "REQUIREMENTS",
            "content": "REQ-001: The system shall ingest PDF and DOCX files. REQ-002: PII must be masked before indexing.",
            "summary": "Functional requirements for ingestion and PII handling.",
            "chunk_index_in_section": 0,
            "has_table": False,
            "has_list": False,
            "has_requirement_id": True,
            "requirement_ids": ["REQ-001", "REQ-002"],
            "semantic_score": 0.88,
            "bm25_score": 5.0,
        },
        {
            "chunk_id": "src_chk_003",
            "document_id": "doc_pdd_001",
            "section_id": "sec_architecture",
            "document_type": "SOURCE",
            "section_type": "ARCHITECTURE",
            "content": _TABLE_CONTENT,
            "summary": "Pipeline stage summary table.",
            "chunk_index_in_section": 0,
            "has_table": True,
            "has_list": False,
            "has_requirement_id": False,
            "requirement_ids": [],
            "semantic_score": 0.75,
            "bm25_score": 3.0,
        },
    ],
    "GUIDELINE": [
        {
            "chunk_id": "gl_chk_001",
            "document_id": "doc_guideline_001",
            "section_id": "sec_security_policy",
            "document_type": "GUIDELINE",
            "section_type": "SECURITY",
            "content": "All data at rest must use AES-256 encryption per the enterprise security standard.",
            "summary": "Encryption requirements for data at rest.",
            "chunk_index_in_section": 0,
            "has_table": False,
            "has_list": False,
            "has_requirement_id": False,
            "requirement_ids": [],
            "semantic_score": 0.82,
            "bm25_score": 4.5,
        },
    ],
}


def _build_candidates(pool_name: str) -> list[SearchCandidate]:
    pool = PoolName[pool_name]
    results = []
    for item in _CANDIDATE_STORE.get(pool_name, []):
        doc = IndexedChunkDocument(
            chunk_id=item["chunk_id"],
            document_id=item["document_id"],
            section_id=item["section_id"],
            document_type=item["document_type"],
            section_type=item["section_type"],
            content=item["content"],
            summary=item.get("summary"),
            chunk_index_in_section=item.get("chunk_index_in_section", 0),
            has_table=item.get("has_table", False),
            has_list=item.get("has_list", False),
            has_requirement_id=item.get("has_requirement_id", False),
            requirement_ids=item.get("requirement_ids", []),
        )
        results.append(SearchCandidate(
            document=doc,
            source_role=pool,
            matched_on="summary",
            semantic_score=item.get("semantic_score"),
            bm25_score=item.get("bm25_score"),
        ))
    return results


class _FullInMemorySearchRepo:
    """
    Returns the full candidate store for all 3 section_ids in Pass 1,
    then the same candidates for Pass 2 (to keep the test deterministic).
    """

    def search_section_discovery(self, *, pool, query, plan, filters=None, top_sections=3):
        return _build_candidates(pool.name)

    def search_chunks_by_section_ids(self, *, pool, query, plan, section_ids, filters=None):
        return _build_candidates(pool.name)

    def flat_search(self, *, pool, query, plan, filters=None):
        return _build_candidates(pool.name)


class _EmptySearchRepo:
    """Returns zero candidates for all calls — triggers fallback path."""

    def search_section_discovery(self, *, pool, query, plan, filters=None, top_sections=3):
        return []

    def search_chunks_by_section_ids(self, *, pool, query, plan, section_ids, filters=None):
        return []

    def flat_search(self, *, pool, query, plan, filters=None):
        return []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def retrieval_service():
    repo = _FullInMemorySearchRepo()
    vector_svc = VectorSearchService(repo)
    return RetrievalService(vector_search_service=vector_svc)


@pytest.fixture()
def empty_retrieval_service():
    repo = _EmptySearchRepo()
    vector_svc = VectorSearchService(repo)
    return RetrievalService(vector_search_service=vector_svc)


def _make_request(*, profile_name: str = "default", semantic_role: str = "overview") -> RetrievalRequest:
    return RetrievalRequest(
        retrieval_id="integration_ret_001",
        section_heading="System Overview",
        section_intent="Describe the high-level architecture and goals of the AI SDLC Engine.",
        semantic_role=semantic_role,
        profile_name=profile_name,
    )


# ---------------------------------------------------------------------------
# Integration: full pipeline
# ---------------------------------------------------------------------------

class TestRetrievalPipelineFullFlow:
    def test_returns_three_outputs(self, retrieval_service):
        """retrieve() must return (EvidenceBundle, RetrievalDiagnostics, RetrievalStatus)."""
        bundle, diagnostics, status = retrieval_service.retrieve(_make_request())
        assert isinstance(bundle, EvidenceBundle)
        assert isinstance(diagnostics, RetrievalDiagnostics)
        assert status in list(RetrievalStatus)

    def test_source_facts_populated(self, retrieval_service):
        bundle, _, _ = retrieval_service.retrieve(_make_request())
        assert len(bundle.source.facts) > 0

    def test_guideline_items_populated(self, retrieval_service):
        bundle, _, _ = retrieval_service.retrieve(_make_request())
        assert len(bundle.guideline.items) > 0

    def test_status_ok_when_facts_present(self, retrieval_service):
        _, _, status = retrieval_service.retrieve(_make_request())
        assert status == RetrievalStatus.OK

    def test_table_evidence_extracted_from_table_chunk(self, retrieval_service):
        bundle, _, _ = retrieval_service.retrieve(_make_request())
        assert len(bundle.source.tables) > 0
        assert bundle.source.tables[0].headers == ["Stage", "Responsibility"]

    def test_requirement_ids_in_bundle(self, retrieval_service):
        bundle, _, _ = retrieval_service.retrieve(_make_request())
        assert "REQ-001" in bundle.requirement_ids
        assert "REQ-002" in bundle.requirement_ids

    def test_evidence_bundle_id_in_diagnostics(self, retrieval_service):
        bundle, diagnostics, _ = retrieval_service.retrieve(_make_request())
        assert diagnostics.evidence_bundle_id == bundle.evidence_bundle_id

    def test_overall_confidence_positive(self, retrieval_service):
        bundle, _, _ = retrieval_service.retrieve(_make_request())
        assert bundle.overall_confidence > 0.0


# ---------------------------------------------------------------------------
# Integration: profile routing
# ---------------------------------------------------------------------------

class TestRetrievalPipelineProfileRouting:
    def test_requirements_profile_resolves(self, retrieval_service):
        req = _make_request(profile_name="requirements", semantic_role="requirement")
        bundle, diagnostics, status = retrieval_service.retrieve(req)
        assert diagnostics.retrieval_id == "integration_ret_001"

    def test_architecture_profile_resolves(self, retrieval_service):
        req = _make_request(profile_name="architecture", semantic_role="architecture")
        bundle, _, status = retrieval_service.retrieve(req)
        assert status in list(RetrievalStatus)

    def test_inline_plan_routed_correctly(self, retrieval_service):
        plan = RetrievalPlan(top_k=3, final_output_top_k=3, guideline_enabled=False)
        req = RetrievalRequest(
            retrieval_id="inline_test",
            section_heading="Security",
            section_intent="What are the security requirements?",
            semantic_role="overview",
            profile_name=None,
            inline_plan=plan,
        )
        bundle, diagnostics, _ = retrieval_service.retrieve(req)
        assert diagnostics.guideline_selected_count == 0


# ---------------------------------------------------------------------------
# Integration: empty results → INSUFFICIENT_EVIDENCE
# ---------------------------------------------------------------------------

class TestRetrievalPipelineEmptyResults:
    def test_insufficient_evidence_when_no_candidates(self, empty_retrieval_service):
        _, _, status = empty_retrieval_service.retrieve(_make_request())
        assert status == RetrievalStatus.INSUFFICIENT_EVIDENCE

    def test_bundle_still_returned_on_empty_results(self, empty_retrieval_service):
        bundle, diagnostics, _ = empty_retrieval_service.retrieve(_make_request())
        assert isinstance(bundle, EvidenceBundle)
        assert bundle.source.facts == []
        assert bundle.guideline.items == []
