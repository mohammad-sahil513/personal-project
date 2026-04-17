# backend/modules/retrieval/contracts/retrieval_contracts.py

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SearchMode(str, Enum):
    HYBRID = "hybrid"
    VECTOR_ONLY = "vector_only"
    KEYWORD_ONLY = "keyword_only"


class RetrievalStatus(str, Enum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    FAILED = "FAILED"


class FallbackPolicy(str, Enum):
    EXPAND_QUERY = "expand_query"
    PARENT_SECTION = "parent_section"
    ESCALATE_INSUFFICIENT = "escalate_insufficient"
    BEST_EFFORT = "best_effort"


class PoolName(str, Enum):
    SOURCE = "SOURCE"
    GUIDELINE = "GUIDELINE"


class RetrievalWarningCode(str, Enum):
    LOW_SUMMARY_COVERAGE = "LOW_SUMMARY_COVERAGE"
    LEGACY_SECTION_TYPE_FALLBACK = "LEGACY_SECTION_TYPE_FALLBACK"
    FALLBACK_USED = "FALLBACK_USED"
    APPENDIX_EXCLUDED = "APPENDIX_EXCLUDED"
    EMPTY_RESULTS = "EMPTY_RESULTS"
    TOO_FEW_SECTION_IDS = "TOO_FEW_SECTION_IDS"
    INLINE_PLAN_IGNORED = "INLINE_PLAN_IGNORED"



class RetrievalFilters(BaseModel):
    """
    Aligned filter inventory for retrieval requests/plans.

    Only fields listed in the aligned retrieval plan are allowed here.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    chunk_id: str | None = None
    document_id: str | None = None
    section_id: str | None = None
    document_type: str | None = None
    section_type: str | None = None
    has_table: bool | None = None
    has_vision_extraction: bool | None = None
    has_list: bool | None = None
    has_requirement_id: bool | None = None
    requirement_ids: list[str] = Field(default_factory=list)

    @field_validator(
        "chunk_id",
        "document_id",
        "section_id",
        "document_type",
        "section_type",
        mode="before",
    )
    @classmethod
    def normalize_string_filters(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("Filter value must be a string or null.")
        value = value.strip()
        return value or None

    @field_validator("requirement_ids", mode="before")
    @classmethod
    def normalize_requirement_ids(cls, value: Any) -> list[str]:
        if value is None:
            return []

        if not isinstance(value, list):
            raise TypeError("requirement_ids must be a list of strings.")

        normalized: list[str] = []
        seen: set[str] = set()

        for item in value:
            if item is None:
                continue
            if not isinstance(item, str):
                raise TypeError("Each requirement_id must be a string.")
            item = item.strip()
            if not item:
                continue
            if item not in seen:
                seen.add(item)
                normalized.append(item)

        return normalized

    def to_filter_dict(self) -> dict[str, Any]:
        """
        Return only populated filter fields for repository/search usage.
        """
        data = self.model_dump(exclude_none=True)
        if not data.get("requirement_ids"):
            data.pop("requirement_ids", None)
        return data


VALID_FILTER_FIELDS = frozenset(RetrievalFilters.model_fields.keys())


class RetrievalPlan(BaseModel):
    """
    Resolved executable retrieval plan.

    Important locked semantics:
    - top_k = SOURCE candidate retrieval size
    - guideline_top_k = GUIDELINE candidate retrieval size
    - final_output_top_k = final result cap after reranking / packaging
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    search_mode: SearchMode = SearchMode.HYBRID
    top_k: int = Field(default=8, ge=1, description="SOURCE candidate retrieval size.")
    guideline_top_k: int = Field(
        default=4,
        ge=0,
        description="GUIDELINE candidate retrieval size.",
    )
    final_output_top_k: int = Field(
        default=8,
        ge=1,
        description="Final cap after reranking / packaging.",
    )
    min_confidence: float = Field(default=0.50, ge=0.0, le=1.0)
    fallback_policy: FallbackPolicy = FallbackPolicy.ESCALATE_INSUFFICIENT
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    include_appendix: bool = False
    max_fallback_attempts: int = Field(default=1, ge=0, le=1)
    source_enabled: bool = True
    guideline_enabled: bool = True

    @model_validator(mode="after")
    def validate_pool_enablement(self) -> "RetrievalPlan":
        if not self.source_enabled and not self.guideline_enabled:
            raise ValueError("At least one retrieval pool must be enabled.")
        return self


class RetrievalRequest(BaseModel):
    """
    Input request for section-oriented retrieval.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    retrieval_id: str = Field(..., description="Correlation identifier for one retrieval call.")
    project_id: str | None = None
    target_section_id: str | None = Field(
        default=None,
        description="Target output section identifier from template/generation context.",
    )
    section_heading: str = Field(..., description="Heading of the output section being generated.")
    section_intent: str = Field(..., description="Intent / user generation goal for the section.")
    semantic_role: str = Field(..., description="Semantic role used by retrieval/query expansion.")
    profile_name: str | None = Field(
        default=None,
        description="Named retrieval profile from registry.",
    )
    inline_plan: RetrievalPlan | None = Field(
        default=None,
        description="Inline retrieval plan when profile is not used.",
    )
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    fallback_policy_override: FallbackPolicy | None = None
    min_confidence_override: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator(
        "retrieval_id",
        "section_heading",
        "section_intent",
        "semantic_role",
        "profile_name",
        "project_id",
        "target_section_id",
        mode="before",
    )
    @classmethod
    def normalize_strings(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("Value must be a string or null.")
        value = value.strip()
        return value or None

    @model_validator(mode="after")
    def ensure_profile_or_inline_plan(self) -> "RetrievalRequest":
        if not self.profile_name and self.inline_plan is None:
            raise ValueError("Either profile_name or inline_plan must be provided.")
        return self


class RetrievalCostSummary(BaseModel):
    """
    Retrieval-level cost continuity placeholder for observability integration.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    query_embedding_tokens: int = Field(default=0, ge=0)
    search_requests_count: int = Field(default=0, ge=0)
    fallback_search_requests_count: int = Field(default=0, ge=0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)


class RetrievalDiagnostics(BaseModel):
    """
    Diagnostics returned alongside retrieval evidence.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    retrieval_id: str
    status: RetrievalStatus
    final_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    min_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    fallback_attempted: bool = False
    fallback_policy_used: FallbackPolicy | None = None
    warnings: list[RetrievalWarningCode] = Field(default_factory=list)
    search_mode: SearchMode = SearchMode.HYBRID
    source_candidate_count: int = Field(default=0, ge=0)
    guideline_candidate_count: int = Field(default=0, ge=0)
    source_selected_count: int = Field(default=0, ge=0)
    guideline_selected_count: int = Field(default=0, ge=0)
    summary_coverage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    legacy_section_type_fallback_used: bool = False
    evidence_bundle_id: str | None = None
    cost_summary: RetrievalCostSummary = Field(default_factory=RetrievalCostSummary)

    @field_validator("retrieval_id")
    @classmethod
    def validate_retrieval_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("retrieval_id cannot be blank.")
        return value


__all__ = [
    "SearchMode",
    "RetrievalStatus",
    "FallbackPolicy",
    "PoolName",
    "RetrievalWarningCode",
    "RetrievalFilters",
    "VALID_FILTER_FIELDS",
    "RetrievalPlan",
    "RetrievalRequest",
    "RetrievalCostSummary",
    "RetrievalDiagnostics",
]
