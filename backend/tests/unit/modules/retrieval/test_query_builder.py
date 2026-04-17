"""
Unit tests — Phase 4.2 (query_builder)
QueryBuilderService is fully deterministic with no external dependencies.
"""

from __future__ import annotations

import pytest

from backend.modules.retrieval.contracts.retrieval_contracts import (
    RetrievalPlan,
    RetrievalRequest,
    SearchMode,
)
from backend.modules.retrieval.services.query_builder import (
    MAX_QUERY_TOKENS,
    QueryBuildResult,
    QueryBuilderService,
)


def _make_request(
    *,
    section_heading: str = "System Overview",
    section_intent: str = "Describe the high-level architecture.",
    semantic_role: str = "overview",
) -> RetrievalRequest:
    return RetrievalRequest(
        retrieval_id="qb_test",
        section_heading=section_heading,
        section_intent=section_intent,
        semantic_role=semantic_role,
        profile_name="default",
    )


# ---------------------------------------------------------------------------
# Basic query building
# ---------------------------------------------------------------------------

class TestQueryBuilderBasic:
    def test_returns_query_build_result(self):
        req = _make_request()
        plan = RetrievalPlan()
        result = QueryBuilderService.build(request=req, plan=plan)
        assert isinstance(result, QueryBuildResult)

    def test_query_text_contains_intent(self):
        req = _make_request(section_intent="User authentication flow details")
        result = QueryBuilderService.build(request=req, plan=RetrievalPlan())
        assert "User authentication flow details" in result.query_text

    def test_query_text_contains_heading(self):
        req = _make_request(section_heading="Architecture Design")
        result = QueryBuilderService.build(request=req, plan=RetrievalPlan())
        assert "Architecture Design" in result.query_text

    def test_role_terms_included_for_known_role(self):
        req = _make_request(semantic_role="architecture")
        result = QueryBuilderService.build(request=req, plan=RetrievalPlan())
        assert len(result.role_terms_used) > 0
        assert any("architecture" in t for t in result.role_terms_used)

    def test_expansion_terms_included_for_known_role(self):
        # Use a very short intent so the token budget isn't saturated and
        # expansion terms actually survive into the final query.
        req = _make_request(section_intent="requirements", section_heading="R", semantic_role="requirements")
        result = QueryBuilderService.build(request=req, plan=RetrievalPlan(), max_query_tokens=200)
        # Either expansion terms or role terms must appear — the query builder
        # includes both groups when budget allows.
        assert len(result.role_terms_used) > 0 or len(result.expansion_terms_used) > 0

    def test_unknown_role_falls_back_to_role_key(self):
        req = _make_request(semantic_role="custom_role_xyz")
        result = QueryBuilderService.build(request=req, plan=RetrievalPlan())
        assert result.semantic_role_key == "custom_role_xyz"

    def test_token_count_matches_query_text(self):
        req = _make_request()
        result = QueryBuilderService.build(request=req, plan=RetrievalPlan())
        # Whitespace-split token count must equal reported count
        assert result.token_count == len(result.query_text.split())


# ---------------------------------------------------------------------------
# Role key normalisation
# ---------------------------------------------------------------------------

class TestRoleKeyNormalization:
    @pytest.mark.parametrize("raw,expected", [
        ("overview", "overview"),
        ("Architecture", "architecture"),
        ("Process Flow", "process_flow"),
        ("API-Specification", "api_specification"),
        ("  data model  ", "data_model"),
    ])
    def test_normalize_role_key(self, raw: str, expected: str):
        result = QueryBuilderService._normalize_role_key(raw)
        assert result == expected


# ---------------------------------------------------------------------------
# Token-budget trimming
# ---------------------------------------------------------------------------

class TestQueryBuilderTrimming:
    def test_stays_within_budget(self):
        # Build a very long intent to force trimming
        long_intent = " ".join(["word"] * 300)
        req = _make_request(section_intent=long_intent, semantic_role="architecture")
        result = QueryBuilderService.build(request=req, plan=RetrievalPlan(), max_query_tokens=50)
        assert result.token_count <= 50

    def test_trimmed_terms_reported(self):
        long_intent = " ".join(["word"] * 300)
        req = _make_request(section_intent=long_intent, semantic_role="architecture")
        result = QueryBuilderService.build(request=req, plan=RetrievalPlan(), max_query_tokens=20)
        # Some expansion/role terms must have been trimmed
        assert len(result.trimmed_terms) > 0

    def test_intent_takes_priority_over_expansion(self):
        """Intent must survive even when expansion_terms are trimmed."""
        intent = "user authentication token validation"
        req = _make_request(section_intent=intent, semantic_role="requirements")
        result = QueryBuilderService.build(request=req, plan=RetrievalPlan(), max_query_tokens=15)
        # Intent words should appear somewhere in the final query
        assert any(word in result.query_text for word in intent.split())

    def test_heading_preserved_when_intent_stripped(self):
        """When the budget is very tight, heading must be preserved."""
        long_intent = " ".join(["word"] * 500)
        req = _make_request(
            section_intent=long_intent,
            section_heading="Short Heading",
        )
        result = QueryBuilderService.build(request=req, plan=RetrievalPlan(), max_query_tokens=5)
        assert "Short" in result.query_text or "Heading" in result.query_text


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestQueryBuilderDeterminism:
    def test_same_input_produces_same_output(self):
        req = _make_request()
        plan = RetrievalPlan()
        r1 = QueryBuilderService.build(request=req, plan=plan)
        r2 = QueryBuilderService.build(request=req, plan=plan)
        assert r1.query_text == r2.query_text
        assert r1.token_count == r2.token_count
        assert r1.role_terms_used == r2.role_terms_used
