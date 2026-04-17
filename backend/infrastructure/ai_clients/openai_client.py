# backend/infrastructure/ai_clients/openai_client.py

from __future__ import annotations

from typing import Any

from openai import AzureOpenAI
from backend.core.config import Settings, get_settings


class AzureOpenAIEmbeddingClient:
    """
    Thin adapter for Azure OpenAI embeddings.

    This adapter is intentionally minimal:
    - one embedding deployment
    - one embed_query(text) method for retrieval
    """

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        deployment_name: str,
        api_version: str = "2024-02-01",
        sdk_client: AzureOpenAI | None = None,
    ) -> None:
        self._endpoint = endpoint
        self._api_key = api_key
        self._deployment_name = deployment_name
        self._api_version = api_version
        self._client = sdk_client or AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )

    @classmethod
    def from_env(
        cls,
        *,
        settings: Settings | None = None,
    ) -> "AzureOpenAIEmbeddingClient":
        resolved_settings = settings or get_settings()
        endpoint = resolved_settings.azure_openai_endpoint
        api_key = resolved_settings.azure_openai_api_key
        deployment_name = resolved_settings.azure_openai_embedding_deployment
        api_version = resolved_settings.azure_openai_api_version

        if not endpoint:
            raise ValueError("Missing required setting: azure_openai_endpoint")
        if not api_key:
            raise ValueError("Missing required setting: azure_openai_api_key")
        if not deployment_name:
            raise ValueError("Missing required setting: azure_openai_embedding_deployment")

        return cls(
            endpoint=endpoint,
            api_key=api_key,
            deployment_name=deployment_name,
            api_version=api_version,
        )

    def embed_query(self, text: str) -> list[float]:
        normalized = " ".join(text.strip().split())
        if not normalized:
            raise ValueError("Query text for embedding cannot be blank.")

        response = self._client.embeddings.create(
            model=self._deployment_name,
            input=normalized,
        )

        if not response.data:
            raise ValueError("Azure OpenAI embeddings response contained no data.")

        embedding = response.data[0].embedding
        return [float(value) for value in embedding]