# backend/modules/retrieval/services/query_builder.py

from __future__ import annotations

import re
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.retrieval.contracts.retrieval_contracts import (
    RetrievalPlan,
    RetrievalRequest,
)

MAX_QUERY_TOKENS = 200


class QueryBuildResult(BaseModel):
    """
    Deterministic query builder output.

    This is an internal retrieval-layer artifact that will later be passed
    into search/retrieval services.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )

    query_text: str = Field(..., description="Final normalized query text.")
    token_count: int = Field(..., ge=0, description="Final token count.")
    semantic_role_key: str = Field(..., description="Normalized semantic role key used for expansion.")
    intent_segment: str = Field(..., description="Normalized intent text.")
    heading_segment: str = Field(..., description="Normalized section heading text.")
    role_terms_used: list[str] = Field(default_factory=list)
    expansion_terms_used: list[str] = Field(default_factory=list)
    trimmed_terms: list[str] = Field(default_factory=list)


class QueryBuilderService:
    """
    Deterministic retrieval query builder.

    Composition priority (highest -> lowest):
    1. section_intent
    2. section_heading
    3. semantic_role terms
    4. expansion terms

    Trimming removes lowest-priority terms first to stay within MAX_QUERY_TOKENS.
    """

    ROLE_TERMS: dict[str, list[str]] = {
        "overview": ["overview", "summary", "business context"],
        "architecture": ["architecture", "components", "integration"],
        "architecture_description": ["architecture", "components", "integration"],
        "process": ["process", "workflow", "sequence"],
        "process_flow": ["process", "workflow", "sequence"],
        "data": ["data model", "schema", "entities"],
        "data_model": ["data model", "schema", "entities"],
        "api": ["api", "endpoint", "request response"],
        "api_specification": ["api", "endpoint", "request response"],
        "requirement": ["requirements", "business rules", "acceptance criteria"],
        "requirements_summary": ["requirements", "business rules", "acceptance criteria"],
    }

    EXPANSION_TERMS: dict[str, list[str]] = {
        "overview": ["scope", "objectives", "functional overview", "system summary"],
        "architecture": ["services", "modules", "dependencies", "interfaces", "integration points"],
        "architecture_description": ["services", "modules", "dependencies", "interfaces", "integration points"],
        "process": ["workflow steps", "sequence of actions", "control flow", "business flow"],
        "process_flow": ["workflow steps", "sequence of actions", "control flow", "business flow"],
        "data": ["tables", "attributes", "relationships", "entities", "data definitions"],
        "data_model": ["tables", "attributes", "relationships", "entities", "data definitions"],
        "api": ["http method", "request payload", "response payload", "status codes", "parameters"],
        "api_specification": ["http method", "request payload", "response payload", "status codes", "parameters"],
        "requirement": ["requirement ids", "constraints", "functional requirements", "non functional requirements"],
        "requirements_summary": ["requirement ids", "constraints", "functional requirements", "non functional requirements"],
    }

    @classmethod
    def build(
        cls,
        request: RetrievalRequest,
        plan: RetrievalPlan,
        max_query_tokens: int = MAX_QUERY_TOKENS,
    ) -> QueryBuildResult:
        """
        Build a deterministic query payload from a resolved request/plan.
        """
        semantic_role_key = cls._normalize_role_key(request.semantic_role)

        intent_segment = cls._normalize_text(request.section_intent)
        heading_segment = cls._normalize_text(request.section_heading)

        role_terms = cls._get_role_terms(semantic_role_key)
        expansion_terms = cls._get_expansion_terms(semantic_role_key)

        # Priority stack: high -> low
        # Each element is a list of segments to preserve order.
        priority_groups: list[tuple[str, list[str]]] = [
            ("intent", [intent_segment] if intent_segment else []),
            ("heading", [heading_segment] if heading_segment else []),
            ("role_terms", role_terms.copy()),
            ("expansion_terms", expansion_terms.copy()),
        ]

        final_segments, trimmed_terms = cls._trim_to_budget(
            priority_groups=priority_groups,
            max_tokens=max_query_tokens,
        )

        query_text = cls._join_segments(final_segments)
        token_count = cls._count_tokens(query_text)

        role_terms_used = [t for t in final_segments if t in role_terms]
        expansion_terms_used = [t for t in final_segments if t in expansion_terms]

        return QueryBuildResult(
            query_text=query_text,
            token_count=token_count,
            semantic_role_key=semantic_role_key,
            intent_segment=intent_segment,
            heading_segment=heading_segment,
            role_terms_used=role_terms_used,
            expansion_terms_used=expansion_terms_used,
            trimmed_terms=trimmed_terms,
        )

    @classmethod
    def _normalize_role_key(cls, semantic_role: str) -> str:
        semantic_role = semantic_role.strip().lower()
        semantic_role = semantic_role.replace("-", "_").replace(" ", "_")
        return semantic_role

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        text = text.strip()
        text = re.sub(r"\s+", " ", text)
        return text

    @classmethod
    def _get_role_terms(cls, semantic_role_key: str) -> list[str]:
        return cls.ROLE_TERMS.get(semantic_role_key, [semantic_role_key.replace("_", " ")])

    @classmethod
    def _get_expansion_terms(cls, semantic_role_key: str) -> list[str]:
        return cls.EXPANSION_TERMS.get(semantic_role_key, [])

    @classmethod
    def _trim_to_budget(
        cls,
        priority_groups: list[tuple[str, list[str]]],
        max_tokens: int,
    ) -> tuple[list[str], list[str]]:
        """
        Preserve higher-priority groups as long as possible.

        Trimming order:
        1. expansion_terms
        2. role_terms
        3. if still too long, preserve heading and trim intent to fit
        4. if heading alone exceeds budget, hard-trim heading
        """
        current_segments = cls._flatten_groups(priority_groups)
        trimmed_terms: list[str] = []

        if cls._count_tokens(cls._join_segments(current_segments)) <= max_tokens:
            return current_segments, trimmed_terms

        # Mutable group copies
        mutable_groups = {name: values[:] for name, values in priority_groups}

        # Step 1: trim only optional groups first
        trim_order = ["expansion_terms", "role_terms"]

        for group_name in trim_order:
            group_values = mutable_groups.get(group_name, [])
            while group_values:
                removed = group_values.pop()  # remove from end
                trimmed_terms.append(removed)
                mutable_groups[group_name] = group_values

                flattened = cls._flatten_groups(
                    [
                        ("intent", mutable_groups.get("intent", [])),
                        ("heading", mutable_groups.get("heading", [])),
                        ("role_terms", mutable_groups.get("role_terms", [])),
                        ("expansion_terms", mutable_groups.get("expansion_terms", [])),
                    ]
                )
                if cls._count_tokens(cls._join_segments(flattened)) <= max_tokens:
                    return flattened, trimmed_terms

        # Step 2: preserve heading + trimmed intent if still over budget
        intent_text = cls._join_segments(mutable_groups.get("intent", []))
        heading_text = cls._join_segments(mutable_groups.get("heading", []))

        intent_tokens = cls._tokenize(intent_text)
        heading_tokens = cls._tokenize(heading_text)

        # If heading itself exceeds the whole budget, keep only heading prefix
        if len(heading_tokens) >= max_tokens:
            return [" ".join(heading_tokens[:max_tokens])], trimmed_terms + ["<intent_trimmed_to_zero>"]

        # Reserve full heading, trim intent to remaining budget
        remaining_for_intent = max_tokens - len(heading_tokens)

        trimmed_intent_tokens = intent_tokens[:remaining_for_intent]
        trimmed_intent_text = " ".join(trimmed_intent_tokens)

        final_segments: list[str] = []
        if trimmed_intent_text:
            final_segments.append(trimmed_intent_text)
        if heading_text:
            final_segments.append(heading_text)

        return final_segments, trimmed_terms
   
    @staticmethod
    def _flatten_groups(priority_groups: Iterable[tuple[str, list[str]]]) -> list[str]:
        segments: list[str] = []
        for _, values in priority_groups:
            for value in values:
                if value:
                    segments.append(value)
        return segments

    @staticmethod
    def _join_segments(segments: list[str]) -> str:
        return " ".join(segment.strip() for segment in segments if segment.strip())

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        # Lightweight deterministic token estimate by whitespace splitting.
        return [token for token in text.split() if token]

    @classmethod
    def _count_tokens(cls, text: str) -> int:
        return len(cls._tokenize(text))
