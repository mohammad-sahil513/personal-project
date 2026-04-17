# backend/modules/retrieval/live_wiring.py

from __future__ import annotations

from dataclasses import dataclass

from backend.core.config import get_settings
from backend.infrastructure.ai_clients.openai_client import AzureOpenAIEmbeddingClient
from backend.infrastructure.search.search_client import AzureAISearchClientAdapter
from backend.modules.observability.services.cost_aggregation_service import (
    CostAggregationService,
)
from backend.modules.observability.services.cost_estimator_service import (
    CostEstimatorService,
)
from backend.modules.observability.services.logging_service import LoggingService
from backend.modules.observability.services.pricing_registry_service import (
    PricingRegistryService,
)
from backend.modules.observability.services.request_context_service import (
    RequestContextService,
)
from backend.modules.retrieval.repositories.search_repository import SearchRepository
from backend.modules.retrieval.services.retrieval_service import RetrievalService
from backend.modules.retrieval.services.vector_search_service import VectorSearchService


@dataclass
class RetrievalRuntime:
    """
    Fully wired live retrieval runtime.
    """

    search_client: AzureAISearchClientAdapter
    embedding_client: AzureOpenAIEmbeddingClient
    search_repository: SearchRepository
    vector_search_service: VectorSearchService
    retrieval_service: RetrievalService

    def close(self) -> None:
        self.search_client.close()


def build_retrieval_runtime() -> RetrievalRuntime:
    """
    Build the live retrieval runtime using environment-based configuration.

    Required env vars are read inside the infrastructure adapters.
    """
    settings = get_settings()
    search_client = AzureAISearchClientAdapter.from_env(settings=settings)
    embedding_client = AzureOpenAIEmbeddingClient.from_env(settings=settings)

    search_repository = SearchRepository(
        search_client=search_client,
        embedding_client=embedding_client,
    )

    vector_search_service = VectorSearchService(
        search_repository=search_repository,
    )

    retrieval_service = RetrievalService(
        vector_search_service=vector_search_service,
        logging_service=LoggingService(
            logger_name="observability.retrieval",
            context_provider=RequestContextService().get_context_dict,
        ),
        cost_estimator_service=CostEstimatorService(
            pricing_registry_service=PricingRegistryService()
        ),
        cost_aggregation_service=CostAggregationService(),
    )

    return RetrievalRuntime(
        search_client=search_client,
        embedding_client=embedding_client,
        search_repository=search_repository,
        vector_search_service=vector_search_service,
        retrieval_service=retrieval_service,
    )