"""
Unit tests — Phase 4.1
Covers: retrieval_contracts, evidence_contracts, index_contracts,
        retrieval_profiles registry, RetrievalProfileResolver.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.modules.retrieval.contracts.retrieval_contracts import (
    FallbackPolicy,
    PoolName,
    RetrievalFilters,
    RetrievalPlan,
    RetrievalRequest,
    SearchMode,
)
from backend.modules.retrieval.contracts.evidence_contracts import (
    EvidenceBundle,
    EvidenceRef,
    FactEvidence,
    GuidelineEvidence,
    GuidelineEvidenceSet,
    SourceEvidence,
    TableEvidence,
    TableType,
)
from backend.modules.retrieval.contracts.index_contracts import IndexedChunkDocument
from backend.modules.retrieval.profiles.retrieval_profiles import (
    RETRIEVAL_PROFILES,
    get_retrieval_profile,
)
from backend.modules.retrieval.services.profile_resolver import (
    ProfileResolutionError,
    RetrievalProfileResolver,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ref(pool: PoolName = PoolName.SOURCE) -> EvidenceRef:
    return EvidenceRef(
        chunk_id="chk_001",
        document_id="doc_001",
        section_id="sec_overview",
        section_type="OVERVIEW",
        chunk_index_in_section=0,
        source_role=pool,
    )


def _make_request(*, profile_name: str | None = "default", inline_plan=None) -> RetrievalRequest:
    return RetrievalRequest(
        retrieval_id="ret_001",
        section_heading="System Overview",
        section_intent="Describe the high-level architecture of the system.",
        semantic_role="overview",
        profile_name=profile_name,
        inline_plan=inline_plan,
    )


# ---------------------------------------------------------------------------
# RetrievalFilters
# ---------------------------------------------------------------------------

class TestRetrievalFilters:
    def test_empty_filters(self):
        f = RetrievalFilters()
        assert f.to_filter_dict() == {}

    def test_string_filters_stripped(self):
        f = RetrievalFilters(document_type="  SOURCE  ")
        assert f.document_type == "SOURCE"

    def test_blank_string_becomes_none(self):
        f = RetrievalFilters(section_id="   ")
        assert f.section_id is None

    def test_requirement_ids_deduped(self):
        f = RetrievalFilters(requirement_ids=["REQ-001", "  REQ-001  ", "REQ-002"])
        assert f.requirement_ids == ["REQ-001", "REQ-002"]

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            RetrievalFilters(unknown_field="bad")

    def test_to_filter_dict_excludes_none_and_empty_list(self):
        f = RetrievalFilters(document_id="doc_1", requirement_ids=[])
        d = f.to_filter_dict()
        assert "requirement_ids" not in d
        assert d["document_id"] == "doc_1"


# ---------------------------------------------------------------------------
# RetrievalPlan
# ---------------------------------------------------------------------------

class TestRetrievalPlan:
    def test_defaults(self):
        plan = RetrievalPlan()
        assert plan.search_mode == SearchMode.HYBRID
        assert plan.top_k == 8
        assert plan.min_confidence == 0.50
        assert plan.source_enabled is True
        assert plan.guideline_enabled is True

    def test_both_pools_disabled_raises(self):
        with pytest.raises(ValidationError):
            RetrievalPlan(source_enabled=False, guideline_enabled=False)

    def test_top_k_minimum_1(self):
        with pytest.raises(ValidationError):
            RetrievalPlan(top_k=0)


# ---------------------------------------------------------------------------
# RetrievalRequest
# ---------------------------------------------------------------------------

class TestRetrievalRequest:
    def test_profile_name_path(self):
        req = _make_request(profile_name="default")
        assert req.profile_name == "default"
        assert req.inline_plan is None

    def test_inline_plan_path(self):
        plan = RetrievalPlan()
        req = _make_request(profile_name=None, inline_plan=plan)
        assert req.inline_plan is not None

    def test_neither_profile_nor_plan_raises(self):
        with pytest.raises(ValidationError):
            RetrievalRequest(
                retrieval_id="r1",
                section_heading="Heading",
                section_intent="Intent",
                semantic_role="overview",
                # neither profile_name nor inline_plan
            )

    def test_strings_stripped(self):
        req = RetrievalRequest(
            retrieval_id="  r1  ",
            section_heading="  Heading  ",
            section_intent="  Intent  ",
            semantic_role="  overview  ",
            profile_name="default",
        )
        assert req.retrieval_id == "r1"
        assert req.section_heading == "Heading"


# ---------------------------------------------------------------------------
# IndexedChunkDocument
# ---------------------------------------------------------------------------

class TestIndexedChunkDocument:
    def test_happy_path(self):
        doc = IndexedChunkDocument(
            chunk_id="chk_1",
            document_id="doc_1",
            section_id="sec_1",
            document_type="SOURCE",
            section_type="OVERVIEW",
            content="Some content here.",
            chunk_index_in_section=0,
        )
        assert doc.has_requirement_id is False

    def test_requirement_ids_auto_sets_flag(self):
        doc = IndexedChunkDocument(
            chunk_id="chk_2",
            document_id="doc_2",
            section_id="sec_2",
            document_type="SOURCE",
            section_type="REQUIREMENTS",
            content="REQ-001 applies.",
            chunk_index_in_section=0,
            requirement_ids=["REQ-001"],
        )
        assert doc.has_requirement_id is True

    def test_blank_content_raises(self):
        with pytest.raises(ValidationError):
            IndexedChunkDocument(
                chunk_id="chk_3",
                document_id="doc_3",
                section_id="sec_3",
                document_type="SOURCE",
                section_type="OVERVIEW",
                content="   ",
                chunk_index_in_section=0,
            )

    def test_empty_embedding_raises(self):
        with pytest.raises(ValidationError):
            IndexedChunkDocument(
                chunk_id="chk_4",
                document_id="doc_4",
                section_id="sec_4",
                document_type="SOURCE",
                section_type="OVERVIEW",
                content="Some content.",
                chunk_index_in_section=0,
                embedding=[],
            )


# ---------------------------------------------------------------------------
# Evidence contracts
# ---------------------------------------------------------------------------

class TestEvidenceContracts:
    def test_fact_evidence_requires_ref(self):
        with pytest.raises(ValidationError):
            FactEvidence(fact_id="f1", text="Some fact.", refs=[])

    def test_fact_evidence_happy_path(self):
        ref = _make_ref()
        fact = FactEvidence(fact_id="f1", text="Some fact.", refs=[ref], confidence=0.85)
        assert fact.confidence == 0.85

    def test_guideline_evidence_requires_ref(self):
        with pytest.raises(ValidationError):
            GuidelineEvidence(guideline_id="g1", text="A guideline.", refs=[])

    def test_table_evidence_row_column_mismatch_raises(self):
        ref = _make_ref()
        with pytest.raises(ValidationError):
            TableEvidence(
                table_id="tbl_1",
                table_type=TableType.OTHER,
                headers=["Col A", "Col B"],
                rows=[["val1"]],        # only 1 cell, 2 headers
                refs=[ref],
            )

    def test_source_evidence_all_refs_must_be_source(self):
        guideline_ref = _make_ref(pool=PoolName.GUIDELINE)
        with pytest.raises(ValidationError):
            SourceEvidence(refs=[guideline_ref])

    def test_guideline_evidence_set_all_refs_must_be_guideline(self):
        source_ref = _make_ref(pool=PoolName.SOURCE)
        with pytest.raises(ValidationError):
            GuidelineEvidenceSet(refs=[source_ref])

    def test_evidence_bundle_blank_id_raises(self):
        with pytest.raises(ValidationError):
            EvidenceBundle(evidence_bundle_id="   ")

    def test_evidence_bundle_requirement_ids_deduped(self):
        bundle = EvidenceBundle(
            evidence_bundle_id="evb_001",
            requirement_ids=["REQ-001", "REQ-001", "REQ-002"],
        )
        assert bundle.requirement_ids == ["REQ-001", "REQ-002"]


# ---------------------------------------------------------------------------
# Retrieval Profiles
# ---------------------------------------------------------------------------

class TestRetrievalProfiles:
    def test_all_named_profiles_valid(self):
        for name, plan in RETRIEVAL_PROFILES.items():
            assert isinstance(plan, RetrievalPlan), f"Profile '{name}' is not a RetrievalPlan"
            assert plan.top_k >= 1
            assert 0.0 <= plan.min_confidence <= 1.0

    def test_get_profile_returns_copy(self):
        p1 = get_retrieval_profile("default")
        p2 = get_retrieval_profile("default")
        p1.top_k = 999
        assert p2.top_k == 8   # mutation did not affect the registry

    def test_unknown_profile_raises_key_error(self):
        with pytest.raises(KeyError):
            get_retrieval_profile("nonexistent_profile_xyz")

    def test_requirements_profile_has_higher_top_k(self):
        req_plan = get_retrieval_profile("requirements")
        default_plan = get_retrieval_profile("default")
        assert req_plan.top_k > default_plan.top_k

    def test_guideline_heavy_uses_keyword_only(self):
        plan = get_retrieval_profile("guideline_heavy")
        assert plan.search_mode == SearchMode.KEYWORD_ONLY


# ---------------------------------------------------------------------------
# RetrievalProfileResolver
# ---------------------------------------------------------------------------

class TestRetrievalProfileResolver:
    def test_resolve_named_profile(self):
        req = _make_request(profile_name="default")
        plan, warnings = RetrievalProfileResolver.resolve(req)
        assert isinstance(plan, RetrievalPlan)
        assert warnings == []

    def test_resolve_inline_plan(self):
        inline = RetrievalPlan(top_k=5)
        req = _make_request(profile_name=None, inline_plan=inline)
        plan, warnings = RetrievalProfileResolver.resolve(req)
        assert plan.top_k == 5

    def test_inline_plan_ignored_warning_when_both_set(self):
        inline = RetrievalPlan(top_k=5)
        req = RetrievalRequest(
            retrieval_id="r1",
            section_heading="Heading",
            section_intent="Intent",
            semantic_role="overview",
            profile_name="default",
            inline_plan=inline,
        )
        plan, warnings = RetrievalProfileResolver.resolve(req)
        from backend.modules.retrieval.contracts.retrieval_contracts import RetrievalWarningCode
        assert RetrievalWarningCode.INLINE_PLAN_IGNORED in warnings

    def test_override_fallback_policy(self):
        req = RetrievalRequest(
            retrieval_id="r1",
            section_heading="H",
            section_intent="I",
            semantic_role="overview",
            profile_name="default",
            fallback_policy_override=FallbackPolicy.BEST_EFFORT,
        )
        plan, _ = RetrievalProfileResolver.resolve(req)
        assert plan.fallback_policy == FallbackPolicy.BEST_EFFORT

    def test_override_min_confidence(self):
        req = RetrievalRequest(
            retrieval_id="r1",
            section_heading="H",
            section_intent="I",
            semantic_role="overview",
            profile_name="default",
            min_confidence_override=0.9,
        )
        plan, _ = RetrievalProfileResolver.resolve(req)
        assert plan.min_confidence == 0.9

    def test_unknown_profile_raises_profile_resolution_error(self):
        req = RetrievalRequest(
            retrieval_id="r1",
            section_heading="H",
            section_intent="I",
            semantic_role="overview",
            profile_name="does_not_exist",
        )
        with pytest.raises(ProfileResolutionError):
            RetrievalProfileResolver.resolve(req)
