"""
Unit tests — Phase 4.2 (evidence_packager)
EvidencePackager is self-contained — no external mocks required.
Covers: happy path, empty inputs, zero-score chunks, cross-section dedup,
        conflict detection, table extraction, and requirement ID aggregation.
"""

from __future__ import annotations

import pytest

from backend.modules.retrieval.contracts.evidence_contracts import (
    EvidenceBundle,
    TableType,
)
from backend.modules.retrieval.contracts.index_contracts import IndexedChunkDocument
from backend.modules.retrieval.contracts.retrieval_contracts import PoolName
from backend.modules.retrieval.repositories.search_repository import SearchCandidate
from backend.modules.retrieval.services.evidence_packager import EvidencePackager


# ---------------------------------------------------------------------------
# Factories
# ---------------------------------------------------------------------------

def _make_candidate(
    chunk_id: str = "chk_001",
    content: str = "The system supports OAuth 2.0 for authentication.",
    section_id: str = "sec_overview",
    section_type: str = "OVERVIEW",
    has_table: bool = False,
    has_list: bool = False,
    requirement_ids: list[str] | None = None,
    semantic_score: float | None = 0.80,
    bm25_score: float | None = 3.0,
    pool: PoolName = PoolName.SOURCE,
    summary: str | None = None,
) -> SearchCandidate:
    doc = IndexedChunkDocument(
        chunk_id=chunk_id,
        document_id="doc_001",
        section_id=section_id,
        document_type="SOURCE",
        section_type=section_type,
        content=content,
        summary=summary,
        chunk_index_in_section=0,
        has_table=has_table,
        has_list=has_list,
        requirement_ids=requirement_ids or [],
    )
    return SearchCandidate(
        document=doc,
        source_role=pool,
        matched_on="content",
        semantic_score=semantic_score,
        bm25_score=bm25_score,
    )


_TABLE_CONTENT = """\
| Stage | Responsibility |
|-------|----------------|
| 1     | Upload         |
| 2     | Parse          |
"""


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestEvidencePackagerHappyPath:
    def test_returns_evidence_bundle(self):
        src = _make_candidate(chunk_id="src_1")
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_001",
            source_candidates=[src],
            guideline_candidates=[],
        )
        assert isinstance(bundle, EvidenceBundle)
        assert bundle.evidence_bundle_id == "evb_001"

    def test_source_facts_populated(self):
        src = _make_candidate(chunk_id="src_1", content="Fact one. Fact two.")
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_001",
            source_candidates=[src],
            guideline_candidates=[],
        )
        assert len(bundle.source.facts) >= 1

    def test_guideline_items_populated(self):
        gl = _make_candidate(
            chunk_id="gl_1",
            content="All data at rest must be AES-256 encrypted.",
            pool=PoolName.GUIDELINE,
        )
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_002",
            source_candidates=[],
            guideline_candidates=[gl],
        )
        assert len(bundle.guideline.items) == 1
        assert "AES-256" in bundle.guideline.items[0].text

    def test_confidence_inferred_from_semantic_scores(self):
        src = _make_candidate(semantic_score=0.90)
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_003",
            source_candidates=[src],
            guideline_candidates=[],
        )
        assert bundle.overall_confidence == pytest.approx(0.90, abs=0.01)

    def test_explicit_overall_confidence_overrides_inferred(self):
        src = _make_candidate(semantic_score=0.30)
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_004",
            source_candidates=[src],
            guideline_candidates=[],
            overall_confidence=0.99,
        )
        assert bundle.overall_confidence == pytest.approx(0.99, abs=0.01)

    def test_fallback_flag_propagated(self):
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_005",
            source_candidates=[],
            guideline_candidates=[],
            fallback_used=True,
        )
        assert bundle.fallback_used is True


# ---------------------------------------------------------------------------
# Edge cases: empty / zero-score inputs
# ---------------------------------------------------------------------------

class TestEvidencePackagerEdgeCases:
    def test_empty_candidates_returns_valid_bundle(self):
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_empty",
            source_candidates=[],
            guideline_candidates=[],
        )
        assert bundle.source.facts == []
        assert bundle.guideline.items == []
        assert bundle.overall_confidence == 0.0

    def test_zero_semantic_score_candidate_included(self):
        src = _make_candidate(chunk_id="zero_sem", semantic_score=0.0, bm25_score=0.0)
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_zero",
            source_candidates=[src],
            guideline_candidates=[],
        )
        # Fact still packaged even if confidence is zero
        assert len(bundle.source.facts) >= 1
        assert bundle.source.facts[0].confidence == pytest.approx(0.0)

    def test_max_facts_budget_enforced(self):
        """More than MAX_SOURCE_FACTS chunks → only 8 facts emitted."""
        candidates = [
            _make_candidate(
                chunk_id=f"chk_{i}",
                content=f"Unique sentence number {i} describing the system behavior.",
            )
            for i in range(20)
        ]
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_budget",
            source_candidates=candidates,
            guideline_candidates=[],
        )
        assert len(bundle.source.facts) <= EvidencePackager.MAX_SOURCE_FACTS

    def test_max_tables_budget_enforced(self):
        candidates = [
            _make_candidate(chunk_id=f"tbl_{i}", content=_TABLE_CONTENT, has_table=True)
            for i in range(5)
        ]
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_tables",
            source_candidates=candidates,
            guideline_candidates=[],
        )
        assert len(bundle.source.tables) <= EvidencePackager.MAX_TABLES


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------

class TestEvidencePackagerDeduplication:
    def test_duplicate_chunk_ids_deduplicated(self):
        """Same chunk_id appearing twice must be collapsed to one."""
        c1 = _make_candidate(chunk_id="dup_001")
        c2 = _make_candidate(chunk_id="dup_001")
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_dedup",
            source_candidates=[c1, c2],
            guideline_candidates=[],
        )
        # Only one representative fact should be packaged from one unique chunk
        chunk_ids_in_refs = [r.chunk_id for fact in bundle.source.facts for r in fact.refs]
        assert chunk_ids_in_refs.count("dup_001") <= 1

    def test_source_chunk_ids_excluded_from_guideline(self):
        """A chunk_id present in SOURCE must not appear in GUIDELINE refs."""
        shared_chunk_id = "shared_001"
        src = _make_candidate(chunk_id=shared_chunk_id, pool=PoolName.SOURCE)
        gl = _make_candidate(chunk_id=shared_chunk_id, pool=PoolName.GUIDELINE)
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_src_precedence",
            source_candidates=[src],
            guideline_candidates=[gl],
        )
        guideline_chunk_ids = [r.chunk_id for item in bundle.guideline.items for r in item.refs]
        assert shared_chunk_id not in guideline_chunk_ids

    def test_duplicate_fact_texts_not_repeated(self):
        """Same content in two chunks → fact text deduplication."""
        identical_content = "OAuth 2.0 is the authentication protocol."
        c1 = _make_candidate(chunk_id="c1", content=identical_content)
        c2 = _make_candidate(chunk_id="c2", content=identical_content)
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_fact_dedup",
            source_candidates=[c1, c2],
            guideline_candidates=[],
        )
        fact_texts = [f.text.lower() for f in bundle.source.facts]
        normalized = [" ".join(t.split()) for t in fact_texts]
        assert len(normalized) == len(set(normalized)), "Duplicate fact texts were not deduplicated"


# ---------------------------------------------------------------------------
# Table extraction
# ---------------------------------------------------------------------------

class TestEvidencePackagerTableExtraction:
    def test_markdown_table_extracted(self):
        src = _make_candidate(chunk_id="tbl_1", content=_TABLE_CONTENT, has_table=True)
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_tbl",
            source_candidates=[src],
            guideline_candidates=[],
        )
        assert len(bundle.source.tables) == 1
        tbl = bundle.source.tables[0]
        assert tbl.headers == ["Stage", "Responsibility"]
        assert len(tbl.rows) == 2

    def test_non_table_chunk_not_packaged_as_table(self):
        src = _make_candidate(chunk_id="no_tbl", content="Plain prose only.", has_table=False)
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_no_tbl",
            source_candidates=[src],
            guideline_candidates=[],
        )
        assert bundle.source.tables == []

    def test_api_section_type_maps_to_api_table(self):
        src = _make_candidate(
            chunk_id="api_tbl",
            content=_TABLE_CONTENT,
            has_table=True,
            section_type="API_SPECIFICATION",
        )
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_api",
            source_candidates=[src],
            guideline_candidates=[],
        )
        assert len(bundle.source.tables) == 1
        assert bundle.source.tables[0].table_type == TableType.API_TABLE


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

class TestEvidencePackagerConflicts:
    def test_no_conflicts_when_no_shared_requirement_ids(self):
        c1 = _make_candidate(chunk_id="c1", requirement_ids=["REQ-001"])
        c2 = _make_candidate(chunk_id="c2", requirement_ids=["REQ-002"])
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_no_conflict",
            source_candidates=[c1, c2],
            guideline_candidates=[],
        )
        assert bundle.source.conflicts == []

    def test_conflict_detected_when_numeric_values_differ(self):
        c1 = _make_candidate(
            chunk_id="c1",
            content="The timeout is 30 seconds.",
            requirement_ids=["REQ-001"],
        )
        c2 = _make_candidate(
            chunk_id="c2",
            content="The timeout is 60 seconds.",
            requirement_ids=["REQ-001"],
        )
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_conflict",
            source_candidates=[c1, c2],
            guideline_candidates=[],
        )
        assert len(bundle.source.conflicts) == 1
        assert "30" in bundle.source.conflicts[0].conflicting_values or \
               "60" in bundle.source.conflicts[0].conflicting_values


# ---------------------------------------------------------------------------
# Requirement ID aggregation
# ---------------------------------------------------------------------------

class TestEvidencePackagerRequirementIds:
    def test_requirement_ids_aggregated_across_pools(self):
        src = _make_candidate(chunk_id="s1", requirement_ids=["REQ-001", "REQ-002"])
        gl = _make_candidate(chunk_id="g1", requirement_ids=["REQ-003"], pool=PoolName.GUIDELINE)
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_reqs",
            source_candidates=[src],
            guideline_candidates=[gl],
        )
        assert "REQ-001" in bundle.requirement_ids
        assert "REQ-002" in bundle.requirement_ids
        assert "REQ-003" in bundle.requirement_ids

    def test_requirement_ids_deduplicated_across_pools(self):
        src = _make_candidate(chunk_id="s1", requirement_ids=["REQ-001"])
        gl = _make_candidate(chunk_id="g1", requirement_ids=["REQ-001"], pool=PoolName.GUIDELINE)
        bundle = EvidencePackager.package(
            evidence_bundle_id="evb_reqs_dedup",
            source_candidates=[src],
            guideline_candidates=[gl],
        )
        assert bundle.requirement_ids.count("REQ-001") == 1
