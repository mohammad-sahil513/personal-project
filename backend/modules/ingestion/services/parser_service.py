"""
Parser service for Stage 2.

This service coordinates:
- document parsing through Azure Document Intelligence in markdown mode
- markdown cleanup
- asset / hyperlink / table extraction
- parse quality reporting
- artifact persistence to the shared Blob container
"""

from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Protocol

from backend.modules.ingestion.contracts.stage_1_contracts import BlobArtifactReference
from backend.modules.ingestion.contracts.stage_2_contracts import (
    AssetRegistry,
    HyperlinkRegistry,
    ParseQualityReport,
    ParseQualityTier,
    Stage2Input,
    Stage2Metrics,
    Stage2Output,
    TableRegistry,
)
from backend.modules.ingestion.exceptions import BlobStorageError, ParsingError
from backend.modules.ingestion.services.asset_extraction_service import AssetExtractionService
from backend.modules.ingestion.services.cleanup_service import CleanupService
from backend.modules.ingestion.services.hyperlink_extraction_service import HyperlinkExtractionService
from backend.modules.ingestion.services.table_extraction_service import TableExtractionService

class DocumentIntelligenceClientProtocol(Protocol):
    """Minimal parsing contract expected from the Document Intelligence wrapper."""

    async def analyze_to_markdown(self, *, source_blob: BlobArtifactReference) -> str:
        """Parse a blob-backed source document and return markdown."""
        ...


class BlobPersistenceClientProtocol(Protocol):
    """Minimal blob persistence contract used by Stage 2."""

    async def upload_bytes(
        self,
        *,
        container_name: str,
        blob_path: str,
        data: bytes,
        content_type: str,
        overwrite: bool = True,
    ) -> BlobArtifactReference:
        """Upload bytes and return a typed blob artifact reference."""
        ...


class ParserService:
    """Service that executes Stage 2 parsing and markdown enrichment."""

    def __init__(
        self,
        *,
        document_intelligence_client: DocumentIntelligenceClientProtocol,
        blob_client: BlobPersistenceClientProtocol,
        blob_container_name: str,
        asset_extraction_service: AssetExtractionService | None = None,
        hyperlink_extraction_service: HyperlinkExtractionService | None = None,
        table_extraction_service: TableExtractionService | None = None,
        cleanup_service: CleanupService | None = None,
        blob_root_prefix: str = "sahil_storage/",
    ) -> None:
        self._document_intelligence_client = document_intelligence_client
        self._blob_client = blob_client
        self._blob_container_name = blob_container_name
        self._asset_extraction_service = asset_extraction_service or AssetExtractionService()
        self._hyperlink_extraction_service = hyperlink_extraction_service or HyperlinkExtractionService()
        self._table_extraction_service = table_extraction_service or TableExtractionService()
        self._cleanup_service = cleanup_service or CleanupService()
        self._blob_root_prefix = blob_root_prefix.rstrip("/") + "/"

    async def parse_document(self, request: Stage2Input) -> Stage2Output:
        """Parse the source document, enrich markdown, persist artifacts, and return Stage 2 output."""
        total_start = perf_counter()

        parse_start = perf_counter()
        raw_markdown = await self._parse_to_markdown(request)
        parse_duration_ms = (perf_counter() - parse_start) * 1000

        enrichment_start = perf_counter()
        cleaned_markdown, cleanup_warnings, embedded_object_count = self._cleanup_service.clean_markdown(
            raw_markdown
        )
        asset_registry = self._asset_extraction_service.extract_assets(cleaned_markdown)
        hyperlink_registry = self._hyperlink_extraction_service.extract_hyperlinks(cleaned_markdown)
        table_registry = self._table_extraction_service.extract_tables(cleaned_markdown)
        parse_quality_report = self._build_parse_quality_report(
            markdown_text=cleaned_markdown,
            asset_registry=asset_registry,
            hyperlink_registry=hyperlink_registry,
            table_registry=table_registry,
            cleanup_warnings=cleanup_warnings,
            embedded_object_count=embedded_object_count,
        )
        enrichment_duration_ms = (perf_counter() - enrichment_start) * 1000

        persistence_start = perf_counter()
        raw_markdown_artifact = await self._persist_text_artifact(
            document_id=request.document_id,
            relative_blob_path="markdown/raw.md",
            text=raw_markdown,
            content_type="text/markdown",
        )
        enriched_markdown_artifact = await self._persist_text_artifact(
            document_id=request.document_id,
            relative_blob_path="markdown/enriched.md",
            text=cleaned_markdown,
            content_type="text/markdown",
        )
        asset_registry_artifact = await self._persist_json_artifact(
            document_id=request.document_id,
            relative_blob_path="assets/assets.json",
            payload=asset_registry.model_dump(mode="json"),
        )
        hyperlink_registry_artifact = await self._persist_json_artifact(
            document_id=request.document_id,
            relative_blob_path="hyperlinks/hyperlinks.json",
            payload=hyperlink_registry.model_dump(mode="json"),
        )
        table_registry_artifact = await self._persist_json_artifact(
            document_id=request.document_id,
            relative_blob_path="tables/tables.json",
            payload=table_registry.model_dump(mode="json"),
        )
        parse_quality_artifact = await self._persist_json_artifact(
            document_id=request.document_id,
            relative_blob_path="quality/parse_quality_report.json",
            payload=parse_quality_report.model_dump(mode="json"),
        )
        persistence_duration_ms = (perf_counter() - persistence_start) * 1000

        total_duration_ms = (perf_counter() - total_start) * 1000
        metrics = Stage2Metrics(
            parse_duration_ms=round(parse_duration_ms, 3),
            enrichment_duration_ms=round(enrichment_duration_ms, 3),
            persistence_duration_ms=round(persistence_duration_ms, 3),
            total_duration_ms=round(total_duration_ms, 3),
        )

        return Stage2Output(
            process_id=request.process_id,
            document_id=request.document_id,
            source_blob=request.source_blob,
            raw_markdown=raw_markdown,
            enriched_markdown=cleaned_markdown,
            raw_markdown_artifact=raw_markdown_artifact,
            enriched_markdown_artifact=enriched_markdown_artifact,
            asset_registry=asset_registry,
            hyperlink_registry=hyperlink_registry,
            table_registry=table_registry,
            parse_quality_report=parse_quality_report,
            asset_registry_artifact=asset_registry_artifact,
            hyperlink_registry_artifact=hyperlink_registry_artifact,
            table_registry_artifact=table_registry_artifact,
            parse_quality_artifact=parse_quality_artifact,
            warnings=[*request.prior_warnings, *parse_quality_report.warnings],
            metrics=metrics,
        )

    async def _parse_to_markdown(self, request: Stage2Input) -> str:
        try:
            markdown = await self._document_intelligence_client.analyze_to_markdown(
                source_blob=request.source_blob
            )
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise ParsingError(
                f"Failed to parse document '{request.file_name}' into markdown."
            ) from exc

        normalized_markdown = markdown.strip()
        if not normalized_markdown:
            raise ParsingError(f"Document '{request.file_name}' produced empty markdown output.")

        return normalized_markdown

    def _build_parse_quality_report(
        self,
        *,
        markdown_text: str,
        asset_registry: AssetRegistry,
        hyperlink_registry: HyperlinkRegistry,
        table_registry: TableRegistry,
        cleanup_warnings,
        embedded_object_count: int,
    ) -> ParseQualityReport:
        heading_count = len(re.findall(r"(?m)^\s*#{1,6}\s+\S+", markdown_text))
        estimated_tokens = self._estimate_tokens(markdown_text)
        quality_tier = self._determine_quality_tier(
            markdown_text=markdown_text,
            heading_count=heading_count,
            estimated_tokens=estimated_tokens,
        )

        return ParseQualityReport(
            heading_count=heading_count,
            image_count=asset_registry.image_count,
            table_count=table_registry.table_count,
            hyperlink_count=hyperlink_registry.hyperlink_count,
            estimated_tokens=estimated_tokens,
            quality_tier=quality_tier,
            embedded_object_detected=embedded_object_count > 0,
            warnings=list(cleanup_warnings),
        )

    def _determine_quality_tier(
        self,
        *,
        markdown_text: str,
        heading_count: int,
        estimated_tokens: int,
    ) -> ParseQualityTier:
        """
        Deterministic parse quality heuristic for Stage 2.

        Stage 7 will perform stricter validation; Stage 2 only emits an early
        quality signal for observability and diagnostics.
        """
        if not markdown_text.strip():
            return ParseQualityTier.DEGRADED

        if heading_count == 0:
            return ParseQualityTier.DEGRADED

        if estimated_tokens < 20:
            return ParseQualityTier.DEGRADED

        return ParseQualityTier.GOOD

    @staticmethod
    def _estimate_tokens(markdown_text: str) -> int:
        """
        Lightweight deterministic token estimate.

        This uses a simple heuristic to stay test-friendly and independent of
        model-specific tokenizers at this stage.
        """
        word_count = len(re.findall(r"\S+", markdown_text))
        return max(1, round(word_count * 1.3))

    async def _persist_text_artifact(
        self,
        *,
        document_id: str,
        relative_blob_path: str,
        text: str,
        content_type: str,
    ) -> BlobArtifactReference:
        return await self._persist_bytes_artifact(
            document_id=document_id,
            relative_blob_path=relative_blob_path,
            data=text.encode("utf-8"),
            content_type=content_type,
        )

    async def _persist_json_artifact(
        self,
        *,
        document_id: str,
        relative_blob_path: str,
        payload: dict,
    ) -> BlobArtifactReference:
        return await self._persist_bytes_artifact(
            document_id=document_id,
            relative_blob_path=relative_blob_path,
            data=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
            content_type="application/json",
        )

    async def _persist_bytes_artifact(
        self,
        *,
        document_id: str,
        relative_blob_path: str,
        data: bytes,
        content_type: str,
    ) -> BlobArtifactReference:
        blob_path = f"{self._blob_root_prefix}ingestion/{document_id}/{relative_blob_path}"

        try:
            return await self._blob_client.upload_bytes(
                container_name=self._blob_container_name,
                blob_path=blob_path,
                data=data,
                content_type=content_type,
                overwrite=True,
            )
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise BlobStorageError(
                "Failed to persist Stage 2 artifact to Azure Blob Storage.",
                context={"document_id": document_id, "blob_path": blob_path},
            ) from exc