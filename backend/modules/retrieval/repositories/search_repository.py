# backend/modules/retrieval/repositories/search_repository.py

from __future__ import annotations

from typing import Any, Iterable, Protocol

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.retrieval.contracts.index_contracts import IndexedChunkDocument
from backend.modules.retrieval.contracts.retrieval_contracts import (
    PoolName,
    RetrievalFilters,
    RetrievalPlan,
    SearchMode,
)
from backend.modules.retrieval.services.query_builder import QueryBuildResult


DEFAULT_SECTION_DISCOVERY_TOP_N = 3

INDEX_SELECT_FIELDS = [
    "chunk_id",
    "document_id",
    "section_id",
    "document_type",
    "section_type",
    "content",
    "summary",
    "chunk_index_in_section",
    "has_table",
    "has_vision_extraction",
    "has_list",
    "has_requirement_id",
    "requirement_ids",
]


class EmbeddingClientProtocol(Protocol):
    def embed_query(self, text: str) -> list[float]:
        ...


class SearchClientProtocol(Protocol):
    def search(self, **kwargs: Any) -> list[dict[str, Any]] | dict[str, Any]:
        ...


class SearchCandidate(BaseModel):
    """
    Repository-level normalized search candidate.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    document: IndexedChunkDocument
    source_role: PoolName
    matched_on: str = Field(
        ...,
        description="What the search emphasized: summary, content, flat, etc.",
    )
    semantic_score: float | None = Field(default=None)
    bm25_score: float | None = Field(default=None)
    raw_score: float | None = Field(default=None)
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class SearchRepository:
    """
    Low-level repository for hybrid retrieval execution support.

    Responsibilities in this phase:
    - build filter expressions
    - build search payloads
    - run search client calls
    - run embedding client calls
    - normalize raw results into SearchCandidate objects

    This repository does NOT make business decisions about fallback, hierarchy,
    confidence, or reranking.
    """

    def __init__(
        self,
        search_client: SearchClientProtocol,
        embedding_client: EmbeddingClientProtocol | None = None,
    ) -> None:
        self._search_client = search_client
        self._embedding_client = embedding_client

    # ---------------------------------------------------------------------
    # Embedding path
    # ---------------------------------------------------------------------
    def get_query_embedding(self, query_text: str) -> list[float] | None:
        """
        Return an embedding for the query text if an embedding client is configured.
        """
        if self._embedding_client is None:
            return None
        return self._embedding_client.embed_query(query_text)

    # ---------------------------------------------------------------------
    # Search entry points
    # ---------------------------------------------------------------------
    def search_section_discovery(
        self,
        *,
        pool: PoolName,
        query: QueryBuildResult,
        plan: RetrievalPlan,
        filters: RetrievalFilters | None = None,
        top_sections: int = DEFAULT_SECTION_DISCOVERY_TOP_N,
    ) -> list[SearchCandidate]:
        """
        Summary-backed pass-1 style search used to discover relevant section_ids.
        """
        payload = self._build_search_payload(
            pool=pool,
            query=query,
            plan=plan,
            filters=filters or plan.filters,
            top=top_sections,
            search_fields=["summary", "content"],
            matched_on="summary",
            section_ids=None,
        )
        raw_results = self._execute_search(payload)
        return self._normalize_candidates(raw_results, pool=pool, matched_on="summary")

    def search_chunks_by_section_ids(
        self,
        *,
        pool: PoolName,
        query: QueryBuildResult,
        plan: RetrievalPlan,
        section_ids: list[str],
        filters: RetrievalFilters | None = None,
    ) -> list[SearchCandidate]:
        """
        Pass-2 style search restricted to selected section_ids.
        """
        top = self._resolve_pool_top(pool=pool, plan=plan)
        payload = self._build_search_payload(
            pool=pool,
            query=query,
            plan=plan,
            filters=filters or plan.filters,
            top=top,
            search_fields=["content", "summary"],
            matched_on="content",
            section_ids=section_ids,
        )
        raw_results = self._execute_search(payload)
        return self._normalize_candidates(raw_results, pool=pool, matched_on="content")

    def flat_search(
        self,
        *,
        pool: PoolName,
        query: QueryBuildResult,
        plan: RetrievalPlan,
        filters: RetrievalFilters | None = None,
    ) -> list[SearchCandidate]:
        """
        Flat search used by later fallback logic when hierarchy is unavailable or insufficient.
        """
        top = self._resolve_pool_top(pool=pool, plan=plan)
        payload = self._build_search_payload(
            pool=pool,
            query=query,
            plan=plan,
            filters=filters or plan.filters,
            top=top,
            search_fields=["content", "summary"],
            matched_on="flat",
            section_ids=None,
        )
        raw_results = self._execute_search(payload)
        return self._normalize_candidates(raw_results, pool=pool, matched_on="flat")

    # ---------------------------------------------------------------------
    # Payload / filter building
    # ---------------------------------------------------------------------
    def build_filter_expression(
        self,
        *,
        filters: RetrievalFilters | None,
        section_ids: list[str] | None = None,
        include_appendix: bool = False,
    ) -> str | None:
        """
        Build an Azure AI Search-style OData filter string.

        This is intentionally simple and deterministic.
        """
        clauses: list[str] = []

        if filters is not None:
            data = filters.to_filter_dict()

            for field_name, value in data.items():
                if field_name == "requirement_ids":
                    if value:
                        req_clauses = [
                            f"requirement_ids/any(r: r eq '{self._escape_string(item)}')"
                            for item in value
                        ]
                        clauses.append(f"({' or '.join(req_clauses)})")
                elif isinstance(value, bool):
                    clauses.append(f"{field_name} eq {str(value).lower()}")
                else:
                    clauses.append(f"{field_name} eq '{self._escape_string(str(value))}'")

        if section_ids:
            section_clauses = [
                f"section_id eq '{self._escape_string(section_id)}'"
                for section_id in section_ids
            ]
            clauses.append(f"({' or '.join(section_clauses)})")

        if not include_appendix:
            clauses.append("section_type ne 'APPENDIX'")

        return " and ".join(clauses) if clauses else None

    def _build_search_payload(
        self,
        *,
        pool: PoolName,
        query: QueryBuildResult,
        plan: RetrievalPlan,
        filters: RetrievalFilters,
        top: int,
        search_fields: list[str],
        matched_on: str,
        section_ids: list[str] | None,
    ) -> dict[str, Any]:
        filter_expression = self.build_filter_expression(
            filters=filters,
            section_ids=section_ids,
            include_appendix=plan.include_appendix,
        )

        payload: dict[str, Any] = {
            "search_text": query.query_text,
            "search_mode": plan.search_mode.value,
            "top": top,
            "search_fields": search_fields,
            "filter": filter_expression,
            "select": INDEX_SELECT_FIELDS,
            "pool": pool.value,
            "matched_on": matched_on,
        }

        # Query embedding is prepared here for hybrid/vector use.
        embedding = None
        if plan.search_mode in {SearchMode.HYBRID, SearchMode.VECTOR_ONLY}:
            embedding = self.get_query_embedding(query.query_text)
        if embedding is not None:
            payload["query_embedding"] = embedding

        return payload

    def _resolve_pool_top(self, *, pool: PoolName, plan: RetrievalPlan) -> int:
        if pool == PoolName.SOURCE:
            return plan.top_k
        if pool == PoolName.GUIDELINE:
            return plan.guideline_top_k
        return plan.top_k

    # ---------------------------------------------------------------------
    # Raw client execution / normalization
    # ---------------------------------------------------------------------
    def _execute_search(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        raw = self._search_client.search(**payload)

        if isinstance(raw, dict):
            results = raw.get("results", [])
            if not isinstance(results, list):
                raise TypeError("search client dict response must contain a list in 'results'.")
            return results

        if not isinstance(raw, list):
            raise TypeError("search client must return a list or a dict with 'results'.")
        return raw

    def _normalize_candidates(
        self,
        raw_results: Iterable[dict[str, Any]],
        *,
        pool: PoolName,
        matched_on: str,
    ) -> list[SearchCandidate]:
        candidates: list[SearchCandidate] = []

        for item in raw_results:
            document_payload = {
                "chunk_id": item.get("chunk_id"),
                "document_id": item.get("document_id"),
                "section_id": item.get("section_id"),
                "document_type": item.get("document_type"),
                "section_type": item.get("section_type"),
                "content": item.get("content"),
                "summary": item.get("summary"),
                "embedding": item.get("embedding"),
                "chunk_index_in_section": item.get("chunk_index_in_section", 0),
                "has_table": item.get("has_table", False),
                "has_vision_extraction": item.get("has_vision_extraction", False),
                "has_list": item.get("has_list", False),
                "has_requirement_id": item.get("has_requirement_id", False),
                "requirement_ids": item.get("requirement_ids", []),
            }

            document = IndexedChunkDocument(**document_payload)

            semantic_score = self._coerce_float(
                item.get("semantic_score", item.get("@search.rerankerScore"))
            )
            bm25_score = self._coerce_float(
                item.get("bm25_score", item.get("@search.score"))
            )
            raw_score = self._coerce_float(item.get("@search.score"))

            candidates.append(
                SearchCandidate(
                    document=document,
                    source_role=pool,
                    matched_on=matched_on,
                    semantic_score=semantic_score,
                    bm25_score=bm25_score,
                    raw_score=raw_score,
                    raw_payload=dict(item),
                )
            )

        return candidates

    # ---------------------------------------------------------------------
    # Utilities
    # ---------------------------------------------------------------------
    @staticmethod
    def _escape_string(value: str) -> str:
        return value.replace("'", "''")

    @staticmethod
    def _coerce_float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None