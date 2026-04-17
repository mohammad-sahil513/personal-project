from __future__ import annotations

import asyncio
import importlib
import json
from pathlib import Path
from typing import Any, cast

from openai import AsyncAzureOpenAI

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, DocumentContentFormat
from azure.core.credentials import AzureKeyCredential
from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from azure.storage.blob import BlobServiceClient, ContentSettings

from backend.modules.ingestion.contracts.stage_1_contracts import BlobArtifactReference
from backend.modules.ingestion.repositories.ingestion_repository import IngestionRepository
from backend.modules.ingestion.services.chunking_service import ChunkingService
from backend.modules.ingestion.services.image_classification_service import (
    ImageClassificationService,
    RuleBasedAmbiguousImageClassifier,
)
from backend.modules.ingestion.services.indexing_service import IndexingService
from backend.modules.ingestion.services.parser_service import ParserService
from backend.modules.ingestion.services.pii_classifier_adapter import SemanticKernelPiiClassifier
from backend.modules.ingestion.services.pii_service import PiiService, RegexPiiCandidateDetector
from backend.modules.ingestion.services.segmentation_service import SegmentationService
from backend.modules.ingestion.services.upload_service import UploadService
from backend.modules.ingestion.services.validation_service import ValidationService
from backend.modules.ingestion.services.vision_extraction_service import VisionExtractionService
from backend.pipeline.orchestrators.ingestion_orchestrator import IngestionOrchestrator
from backend.infrastructure.ai_clients.sk_unified_adapter import AzureSemanticKernelTextAdapter
from backend.core.config import get_settings
from backend.modules.ingestion.observability.observed_runners import (
    ObservedStageRunner,
    default_safe_metadata_builder,
)
from backend.modules.ingestion.observability.models import IngestionRunContext
from backend.modules.ingestion.observability.observer import IngestionObserverProtocol


class BlobClientAdapter:
    def __init__(self, *, blob_service_client: BlobServiceClient) -> None:
        self._blob_service_client = blob_service_client

    async def upload_bytes(
        self,
        *,
        container_name: str,
        blob_path: str,
        data: bytes,
        content_type: str,
        overwrite: bool = True,
    ) -> BlobArtifactReference:
        blob_client = self._blob_service_client.get_blob_client(container=container_name, blob=blob_path)
        blob_client.upload_blob(
            data,
            overwrite=overwrite,
            content_settings=ContentSettings(content_type=content_type),
        )
        return BlobArtifactReference(
            container_name=container_name,
            blob_path=blob_path,
            content_type=content_type,
            size_bytes=len(data),
            url=blob_client.url,
        )

    def download_bytes(self, *, container_name: str, blob_path: str) -> bytes:
        blob_client = self._blob_service_client.get_blob_client(container=container_name, blob=blob_path)
        return blob_client.download_blob().readall()


class DocumentIntelligenceAdapter:
    def __init__(
        self,
        *,
        document_intelligence_client: DocumentIntelligenceClient,
        blob_adapter: BlobClientAdapter,
        container_name: str,
    ) -> None:
        self._document_intelligence_client = document_intelligence_client
        self._blob_adapter = blob_adapter
        self._container_name = container_name

    async def analyze_to_markdown(self, *, source_blob: BlobArtifactReference) -> str:
        source_bytes = self._blob_adapter.download_bytes(
            container_name=self._container_name,
            blob_path=source_blob.blob_path,
        )
        poller = self._document_intelligence_client.begin_analyze_document(
            "prebuilt-layout",
            AnalyzeDocumentRequest(bytes_source=source_bytes),
            output_content_format=DocumentContentFormat.MARKDOWN,
        )
        result = poller.result()
        return (result.content or "").strip()


class LiveEmbeddingClient:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        deployment_name: str,
    ) -> None:
        self._deployment_name = deployment_name
        self._client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version="2024-10-21",
        )

    async def embed_texts(self, *, texts: list[str]) -> list[list[float]]:
        response = await self._client.embeddings.create(
            model=self._deployment_name,
            input=texts,
        )
        return [list(item.embedding) for item in response.data]


class SearchClientAdapter:
    def __init__(self, *, search_client: SearchClient) -> None:
        self._search_client = search_client

    async def upsert_documents(
        self,
        *,
        index_name: str,
        documents: list[dict],
    ) -> int:
        # The client is already bound to a specific index. Keep this explicit.
        client_index_name = getattr(self._search_client, "_index_name", None)
        if client_index_name and client_index_name != index_name:
            raise ValueError(
                f"Requested index '{index_name}' does not match SearchClient index '{client_index_name}'."
            )

        results = self._search_client.merge_or_upload_documents(documents=documents)
        return sum(1 for result in results if getattr(result, "succeeded", False))


class LiveSemanticKernelPromptExecutor:
    def __init__(
        self,
        *,
        settings,
        endpoint: str,
        api_key: str,
        deployment_name: str,
        api_version: str = "2024-10-21",
    ) -> None:
        self._adapter = AzureSemanticKernelTextAdapter(
            settings=settings,
            endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
            deployments=[
                {"alias": "gpt5mini", "deployment_name": deployment_name},
                {"alias": "gpt5", "deployment_name": deployment_name},
                {"alias": deployment_name, "deployment_name": deployment_name},
            ],
            default_deployment_alias="gpt5mini",
        )

    async def invoke_prompt(
        self,
        *,
        prompt_template: str,
        arguments: dict[str, Any],
        service_id: str,
    ) -> str:
        rendered_prompt = prompt_template
        for key, value in arguments.items():
            rendered_prompt = rendered_prompt.replace(f"{{{{{key}}}}}", str(value))
            rendered_prompt = rendered_prompt.replace(f"{{{{${key}}}}}", str(value))

        response = await asyncio.to_thread(
            self._adapter.invoke_text,
            prompt_text=rendered_prompt,
            model_preference=service_id,
            reasoning_effort="medium",
            verbosity="low",
        )
        return str(response.get("text", "")).strip()


class LocalSmokeVisionExtractor:
    """
    Deterministic local Stage 5 extractor.

    This keeps the current script aligned with the validated smoke architecture:
    real Azure at the outer boundaries, deterministic Stage 4/5 in the middle.
    """

    async def extract_asset(self, *, asset) -> dict:
        title = asset.alt_text or "diagram"
        if getattr(asset.classification, "value", str(asset.classification)) == "FLOWCHART":
            return {
                "title": title,
                "nodes": ["Start", "Decision", "End"],
                "edges": ["Start->Decision", "Decision->End"],
            }
        if getattr(asset.classification, "value", str(asset.classification)) == "ARCHITECTURE":
            return {
                "title": title,
                "nodes": ["UI", "API", "DB"],
                "edges": ["UI->API", "API->DB"],
            }
        return {
            "title": title,
            "nodes": ["A", "B"],
            "edges": ["A->B"],
        }


def build_ingestion_stage_runners(*, repo_dir: Path):
    settings = get_settings()

    missing: list[str] = []
    if not settings.azure_storage_container_name:
        missing.append("azure_storage_container_name")
    if not (settings.azure_storage_connection_string or settings.azure_storage_account_url):
        missing.append("azure_storage_connection_string or azure_storage_account_url")
    if not settings.azure_document_intelligence_endpoint:
        missing.append("azure_document_intelligence_endpoint")
    if not settings.azure_search_endpoint:
        missing.append("azure_search_endpoint")
    if not settings.azure_openai_endpoint:
        missing.append("azure_openai_endpoint")
    if not settings.azure_openai_api_key:
        missing.append("azure_openai_api_key")
    if not settings.azure_openai_embedding_deployment:
        missing.append("azure_openai_embedding_deployment")
    if missing:
        raise RuntimeError(
            "Missing required ingestion bootstrap settings: " + ", ".join(missing)
        )

    if settings.azure_storage_connection_string:
        blob_service_client = BlobServiceClient.from_connection_string(settings.azure_storage_connection_string)
    else:
        blob_service_client = BlobServiceClient(
            account_url=cast(str, settings.azure_storage_account_url),
            credential=DefaultAzureCredential(),
        )

    if settings.azure_document_intelligence_key:
        di_client = DocumentIntelligenceClient(
            endpoint=cast(str, settings.azure_document_intelligence_endpoint),
            credential=AzureKeyCredential(settings.azure_document_intelligence_key),
        )
    else:
        di_client = DocumentIntelligenceClient(
            endpoint=cast(str, settings.azure_document_intelligence_endpoint),
            credential=DefaultAzureCredential(),
        )

    if settings.azure_search_api_key:
        search_credential = AzureKeyCredential(settings.azure_search_api_key)
    else:
        search_credential = DefaultAzureCredential()

    search_client = SearchClient(
        endpoint=cast(str, settings.azure_search_endpoint),
        index_name=settings.azure_search_index_name,
        credential=search_credential,
    )

    repository = IngestionRepository(repo_dir)
    # repo is async; caller initializes.

    blob_adapter = BlobClientAdapter(blob_service_client=blob_service_client)

    stage3_prompt_path = Path("backend/prompts/ingestion/pii_classification_v1.yaml")

    UploadAndDedupStage = getattr(
        importlib.import_module("backend.modules.ingestion.stages.01_upload_and_dedup"),
        "UploadAndDedupStage",
    )
    ParseDocumentStage = getattr(
        importlib.import_module("backend.modules.ingestion.stages.02_parse_document"),
        "ParseDocumentStage",
    )
    MaskPiiStage = getattr(
        importlib.import_module("backend.modules.ingestion.stages.03_mask_pii"),
        "MaskPiiStage",
    )
    ClassifyImagesStage = getattr(
        importlib.import_module("backend.modules.ingestion.stages.04_classify_images"),
        "ClassifyImagesStage",
    )
    VisionExtractionStage = getattr(
        importlib.import_module("backend.modules.ingestion.stages.05_vision_extraction"),
        "VisionExtractionStage",
    )
    SegmentSectionsStage = getattr(
        importlib.import_module("backend.modules.ingestion.stages.06_segment_sections"),
        "SegmentSectionsStage",
    )
    ValidateOutputsStage = getattr(
        importlib.import_module("backend.modules.ingestion.stages.07_validate_outputs"),
        "ValidateOutputsStage",
    )
    SemanticChunkingStage = getattr(
        importlib.import_module("backend.modules.ingestion.stages.08_semantic_chunking"),
        "SemanticChunkingStage",
    )
    VectorIndexingStage = getattr(
        importlib.import_module("backend.modules.ingestion.stages.09_vector_indexing"),
        "VectorIndexingStage",
    )

    stage_1_runner = UploadAndDedupStage(
        UploadService(
            blob_client=blob_adapter,
            repository=repository,
            blob_container_name=cast(str, settings.azure_storage_container_name),
            blob_root_prefix=f"{settings.azure_storage_root_prefix_normalized}/",
        )
    )

    stage_2_runner = ParseDocumentStage(
        parser_service=ParserService(
            document_intelligence_client=DocumentIntelligenceAdapter(
                document_intelligence_client=di_client,
                blob_adapter=blob_adapter,
                container_name=cast(str, settings.azure_storage_container_name),
            ),
            blob_client=blob_adapter,
            blob_container_name=cast(str, settings.azure_storage_container_name),
            blob_root_prefix=f"{settings.azure_storage_root_prefix_normalized}/",
        ),
        repository=repository,
    )

    stage_3_runner = MaskPiiStage(
        pii_service=PiiService(
            candidate_detector=RegexPiiCandidateDetector(),
            classifier=SemanticKernelPiiClassifier(
                prompt_executor=LiveSemanticKernelPromptExecutor(
                    settings=settings,
                    endpoint=cast(str, settings.azure_openai_endpoint),
                    api_key=cast(str, settings.azure_openai_api_key),
                    deployment_name=settings.azure_openai_stage3_chat_deployment,
                    api_version=settings.azure_openai_api_version,
                ),
                prompt_template_path=stage3_prompt_path,
                deployment_name=settings.azure_openai_stage3_chat_deployment,
                prompt_version="live_stage3_test_prompt_v1",
            ),
            blob_client=blob_adapter,
            blob_container_name=cast(str, settings.azure_storage_container_name),
            blob_root_prefix=f"{settings.azure_storage_root_prefix_normalized}/",
        ),
        repository=repository,
    )

    stage_4_runner = ClassifyImagesStage(
        image_classification_service=ImageClassificationService(
            ambiguous_classifier=RuleBasedAmbiguousImageClassifier(),
            blob_client=blob_adapter,
            blob_container_name=cast(str, settings.azure_storage_container_name),
            blob_root_prefix=f"{settings.azure_storage_root_prefix_normalized}/",
        ),
        repository=repository,
    )

    stage_5_runner = VisionExtractionStage(
        vision_extraction_service=VisionExtractionService(
            vision_extractor=LocalSmokeVisionExtractor(),
            blob_client=blob_adapter,
            blob_container_name=cast(str, settings.azure_storage_container_name),
            blob_root_prefix=f"{settings.azure_storage_root_prefix_normalized}/",
        ),
        repository=repository,
    )

    stage_6_runner = SegmentSectionsStage(
        segmentation_service=SegmentationService(),
        repository=repository,
    )

    stage_7_runner = ValidateOutputsStage(
        validation_service=ValidationService(),
        repository=repository,
    )

    stage_8_runner = SemanticChunkingStage(
        chunking_service=ChunkingService(),
        repository=repository,
    )

    stage_9_runner = VectorIndexingStage(
        indexing_service=IndexingService(
            embedding_client=LiveEmbeddingClient(
                endpoint=cast(str, settings.azure_openai_endpoint),
                api_key=cast(str, settings.azure_openai_api_key),
                deployment_name=cast(str, settings.azure_openai_embedding_deployment),
            ),
            search_client=SearchClientAdapter(search_client=search_client),
        ),
        repository=repository,
    )

    return repository, {
        "stage_1_runner": stage_1_runner,
        "stage_2_runner": stage_2_runner,
        "stage_3_runner": stage_3_runner,
        "stage_4_runner": stage_4_runner,
        "stage_5_runner": stage_5_runner,
        "stage_6_runner": stage_6_runner,
        "stage_7_runner": stage_7_runner,
        "stage_8_runner": stage_8_runner,
        "stage_9_runner": stage_9_runner,
    }


def build_observed_orchestrator(
    *,
    stage_runners: dict[str, Any],
    observer: IngestionObserverProtocol | None = None,
    context: IngestionRunContext | None = None,
) -> IngestionOrchestrator:
    resolved_stage_runners = stage_runners
    if observer is not None and context is not None:
        resolved_stage_runners = {
            stage_name: ObservedStageRunner(
                stage_name=stage_name,
                inner_runner=runner,
                observer=observer,
                safe_metadata_builder=default_safe_metadata_builder,
                context=context,
            )
            for stage_name, runner in stage_runners.items()
        }
    return IngestionOrchestrator(**resolved_stage_runners)