# backend/modules/retrieval/profiles/retrieval_profiles.py

from __future__ import annotations

from backend.modules.retrieval.contracts.retrieval_contracts import (
    FallbackPolicy,
    RetrievalPlan,
    SearchMode,
)

# NOTE:
# These are DEFAULTS only.
# Callers may override via profile overrides (handled in profile_resolver).


RETRIEVAL_PROFILES: dict[str, RetrievalPlan] = {
    # Generic default for overview-style sections
    "default": RetrievalPlan(
        search_mode=SearchMode.HYBRID,
        top_k=8,
        guideline_top_k=4,
        final_output_top_k=8,
        min_confidence=0.50,
        fallback_policy=FallbackPolicy.ESCALATE_INSUFFICIENT,
        source_enabled=True,
        guideline_enabled=True,
    ),
    # Architecture-heavy sections
    "architecture": RetrievalPlan(
        search_mode=SearchMode.HYBRID,
        top_k=10,
        guideline_top_k=4,
        final_output_top_k=8,
        min_confidence=0.55,
        fallback_policy=FallbackPolicy.EXPAND_QUERY,
        source_enabled=True,
        guideline_enabled=True,
    ),
    # Requirements-focused sections
    "requirements": RetrievalPlan(
        search_mode=SearchMode.HYBRID,
        top_k=12,
        guideline_top_k=3,
        final_output_top_k=10,
        min_confidence=0.60,
        fallback_policy=FallbackPolicy.PARENT_SECTION,
        source_enabled=True,
        guideline_enabled=True,
    ),
    # Guideline-heavy sections (policies, standards)
    "guideline_heavy": RetrievalPlan(
        search_mode=SearchMode.KEYWORD_ONLY,
        top_k=6,
        guideline_top_k=6,
        final_output_top_k=6,
        min_confidence=0.50,
        fallback_policy=FallbackPolicy.BEST_EFFORT,
        source_enabled=True,
        guideline_enabled=True,
    ),
    # Table-oriented sections produced by section planner.
    "table": RetrievalPlan(
        search_mode=SearchMode.HYBRID,
        top_k=10,
        guideline_top_k=4,
        final_output_top_k=8,
        min_confidence=0.55,
        fallback_policy=FallbackPolicy.EXPAND_QUERY,
        source_enabled=True,
        guideline_enabled=True,
    ),
    # Diagram-oriented sections produced by section planner.
    "diagram": RetrievalPlan(
        search_mode=SearchMode.HYBRID,
        top_k=10,
        guideline_top_k=4,
        final_output_top_k=8,
        min_confidence=0.55,
        fallback_policy=FallbackPolicy.EXPAND_QUERY,
        source_enabled=True,
        guideline_enabled=True,
    ),
    # API-oriented sections inferred by section planner title heuristics.
    "api": RetrievalPlan(
        search_mode=SearchMode.HYBRID,
        top_k=10,
        guideline_top_k=4,
        final_output_top_k=8,
        min_confidence=0.55,
        fallback_policy=FallbackPolicy.EXPAND_QUERY,
        source_enabled=True,
        guideline_enabled=True,
    ),
}


def get_retrieval_profile(profile_name: str) -> RetrievalPlan:
    """
    Return a copy of a named retrieval profile.

    Raises KeyError if profile does not exist.
    """
    profile = RETRIEVAL_PROFILES.get(profile_name)
    if profile is None:
        raise KeyError(f"Unknown retrieval profile: {profile_name}")

    # Important: return a COPY so callers can't mutate the registry
    return profile.model_copy(deep=True)