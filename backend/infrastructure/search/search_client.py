# backend/infrastructure/search/search_client.py

from __future__ import annotations

from typing import Any

from backend.core.config import Settings, get_settings

from azure.core.credentials import AzureKeyCredential

try:
    from azure.identity import DefaultAzureCredential
except Exception:  # pragma: no cover
    DefaultAzureCredential = None  # type: ignore

from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from dotenv import load_dotenv
load_dotenv()

class AzureAISearchClientAdapter:
    """
    Thin adapter around azure.search.documents.SearchClient.

    Important behavior:
    - accepts the internal retrieval repository payload shape
    - translates hybrid/vector/keyword modes into Azure SDK args
    - strips internal-only fields like pool/matched_on
    """

    def __init__(
        self,
        *,
        endpoint: str,
        index_name: str,
        credential: Any,
        vector_field_name: str = "embedding",
        sdk_client: SearchClient | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._index_name = index_name
        self._credential = credential
        self._vector_field_name = vector_field_name
        self._client = sdk_client or SearchClient(
            endpoint=endpoint,
            index_name=index_name,
            credential=credential,
        )

    @classmethod
    def from_env(
        cls,
        *,
        settings: Settings | None = None,
    ) -> "AzureAISearchClientAdapter":
        resolved_settings = settings or get_settings()
        endpoint = resolved_settings.azure_search_endpoint
        index_name = resolved_settings.azure_search_index_name
        api_key = resolved_settings.azure_search_api_key
        vector_field_name = resolved_settings.azure_search_vector_field

        if not endpoint:
            raise ValueError("Missing required setting: azure_search_endpoint")
        if not index_name:
            raise ValueError("Missing required setting: azure_search_index_name")

        if api_key:
            credential = AzureKeyCredential(api_key)
        else:
            if DefaultAzureCredential is None:
                raise ValueError(
                    "No Azure search API key found and azure.identity is unavailable."
                )
            credential = DefaultAzureCredential()

        return cls(
            endpoint=endpoint,
            index_name=index_name,
            credential=credential,
            vector_field_name=vector_field_name,
        )

    def search(self, **kwargs: Any) -> list[dict[str, Any]]:
        """
        Execute a search against Azure AI Search.

        Accepted internal payload keys (from current SearchRepository):
        - search_text
        - search_mode: hybrid | vector_only | keyword_only
        - filter
        - search_fields
        - select
        - top
        - query_embedding
        - pool (ignored)
        - matched_on (ignored)
        """
        internal_mode = kwargs.pop("search_mode", "hybrid")
        query_embedding = kwargs.pop("query_embedding", None)

        # Internal-only metadata from repository payload
        kwargs.pop("pool", None)
        kwargs.pop("matched_on", None)

        search_text = kwargs.pop("search_text", None)
        filter_expression = kwargs.pop("filter", None)
        search_fields = kwargs.pop("search_fields", None)
        select = kwargs.pop("select", None)
        top = kwargs.pop("top", None)

        sdk_kwargs: dict[str, Any] = {}

        if filter_expression is not None:
            sdk_kwargs["filter"] = filter_expression
        if search_fields is not None:
            sdk_kwargs["search_fields"] = search_fields
        if select is not None:
            sdk_kwargs["select"] = select
        if top is not None:
            sdk_kwargs["top"] = top

        # Translate current internal mode to Azure SDK search args.
        if internal_mode == "keyword_only":
            sdk_search_text = search_text or "*"

        elif internal_mode == "vector_only":
            sdk_search_text = None
            if query_embedding is None:
                raise ValueError("vector_only mode requires query_embedding.")
            sdk_kwargs["vector_queries"] = [
                VectorizedQuery(
                    vector=query_embedding,
                    k_nearest_neighbors=top or 3,
                    fields=self._vector_field_name,
                )
            ]

        elif internal_mode == "hybrid":
            sdk_search_text = search_text or "*"
            if query_embedding is not None:
                sdk_kwargs["vector_queries"] = [
                    VectorizedQuery(
                        vector=query_embedding,
                        k_nearest_neighbors=top or 3,
                        fields=self._vector_field_name,
                    )
                ]
        else:
            raise ValueError(f"Unsupported internal search_mode: {internal_mode}")

        results = self._client.search(search_text=sdk_search_text, **sdk_kwargs)
        return [self._result_to_dict(item) for item in results]

    def close(self) -> None:
        try:
            self._client.close()
        except AttributeError:
            return

    @staticmethod
    def _result_to_dict(item: Any) -> dict[str, Any]:
        """
        Normalize Azure SDK result items into plain dictionaries.
        """
        if isinstance(item, dict):
            return dict(item)

        if hasattr(item, "items"):
            try:
                return dict(item.items())
            except Exception:
                pass

        try:
            return dict(item)
        except Exception as exc:
            raise TypeError("Unable to convert search result item to dict.") from exc