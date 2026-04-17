"""
Vision extraction service for Stage 5.

This service performs:
- selection of vision-eligible assets from the Stage 4-classified asset registry
- priority ordering across eligible assets
- enforcement of the max-vision-call cap
- validation of extracted JSON
- deterministic summary generation
- [VISION_EXTRACTED: ...] block injection into markdown
- persistence of the enriched markdown and extraction manifest
"""

from __future__ import annotations

import json
from time import perf_counter
from typing import Protocol

from backend.modules.ingestion.contracts.stage_1_contracts import BlobArtifactReference, StageWarning
from backend.modules.ingestion.contracts.stage_2_contracts import (
    AssetClassification,
    AssetRecord,
    AssetRegistry,
)
from backend.modules.ingestion.contracts.stage_5_contracts import (
    Stage5Input,
    Stage5Metrics,
    Stage5Output,
    VisionExtractionRecord,
    VisionExtractionStatus,
)
from backend.modules.ingestion.exceptions import BlobStorageError, VisionExtractionError


class VisionExtractorProtocol(Protocol):
    """Minimal extractor contract for eligible Stage 5 assets."""

    async def extract_asset(
        self,
        *,
        asset: AssetRecord,
    ) -> dict:
        """
        Return a JSON-serializable extraction payload for the asset.

        The returned payload must be a non-empty dictionary so Stage 5 can
        validate it and inject a deterministic [VISION_EXTRACTED: ...] block.
        """
        ...


class BlobPersistenceClientProtocol(Protocol):
    """Minimal blob persistence contract used by Stage 5."""

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


class VisionExtractionService:
    """Service that executes Stage 5 selective vision extraction."""

    _PRIORITY_ORDER: dict[AssetClassification, int] = {
        AssetClassification.FLOWCHART: 1,
        AssetClassification.ARCHITECTURE: 2,
        AssetClassification.SEQUENCE: 3,
        AssetClassification.GENERIC_DIAGRAM: 4,
    }

    def __init__(
        self,
        *,
        vision_extractor: VisionExtractorProtocol,
        blob_client: BlobPersistenceClientProtocol,
        blob_container_name: str,
        blob_root_prefix: str = "sahil_storage/",
    ) -> None:
        self._vision_extractor = vision_extractor
        self._blob_client = blob_client
        self._blob_container_name = blob_container_name
        self._blob_root_prefix = blob_root_prefix.rstrip("/") + "/"

    async def extract_vision(self, request: Stage5Input) -> Stage5Output:
        """Run selective vision extraction and inject [VISION_EXTRACTED: ...] blocks."""
        total_start = perf_counter()

        vision_enriched_markdown = request.masked_markdown
        extraction_records: list[VisionExtractionRecord] = []
        warnings = list(request.prior_warnings)

        eligible_assets = self._get_priority_sorted_eligible_assets(request.asset_registry)
        extraction_start = perf_counter()

        attempted_calls = 0
        completed_extractions = 0
        skipped_by_cap = 0
        failures = 0

        for asset in request.asset_registry.assets:
            if asset.classification not in self._PRIORITY_ORDER:
                extraction_records.append(
                    VisionExtractionRecord(
                        asset_id=asset.asset_id,
                        classification=asset.classification,
                        status=VisionExtractionStatus.SKIPPED_NOT_ELIGIBLE,
                        priority_rank=None,
                        extraction_payload=None,
                        extraction_summary=None,
                        injected_block=None,
                        reason="Asset is not vision-eligible under the Stage 5 policy.",
                    )
                )

        for asset in eligible_assets:
            priority_rank = self._PRIORITY_ORDER[asset.classification]

            if attempted_calls >= request.max_vision_calls:
                skipped_by_cap += 1
                extraction_records.append(
                    VisionExtractionRecord(
                        asset_id=asset.asset_id,
                        classification=asset.classification,
                        status=VisionExtractionStatus.SKIPPED_CALL_CAP,
                        priority_rank=priority_rank,
                        extraction_payload=None,
                        extraction_summary=None,
                        injected_block=None,
                        reason="Vision extraction skipped because the document call cap was reached.",
                    )
                )
                continue

            attempted_calls += 1

            try:
                extraction_payload = await self._vision_extractor.extract_asset(asset=asset)
                self._validate_extraction_payload(asset=asset, payload=extraction_payload)
                extraction_summary = self._build_deterministic_summary(extraction_payload)
                injected_block = self._build_injected_block(
                    asset=asset,
                    extraction_payload=extraction_payload,
                    extraction_summary=extraction_summary,
                )

                vision_enriched_markdown, injection_succeeded = self._inject_after_placeholder(
                    markdown_text=vision_enriched_markdown,
                    placeholder=asset.placeholder,
                    injected_block=injected_block,
                )

                if not injection_succeeded:
                    failures += 1
                    warnings.append(
                        StageWarning(
                            code="VISION_PLACEHOLDER_NOT_FOUND",
                            message="Vision extraction succeeded but the original asset placeholder was not found for injection.",
                            details={
                                "asset_id": asset.asset_id,
                                "placeholder": asset.placeholder,
                            },
                        )
                    )
                    extraction_records.append(
                        VisionExtractionRecord(
                            asset_id=asset.asset_id,
                            classification=asset.classification,
                            status=VisionExtractionStatus.FAILED,
                            priority_rank=priority_rank,
                            extraction_payload=extraction_payload,
                            extraction_summary=extraction_summary,
                            injected_block=None,
                            reason="Extraction payload was created, but markdown injection failed because the placeholder was not found.",
                        )
                    )
                    continue

                completed_extractions += 1
                extraction_records.append(
                    VisionExtractionRecord(
                        asset_id=asset.asset_id,
                        classification=asset.classification,
                        status=VisionExtractionStatus.EXTRACTED,
                        priority_rank=priority_rank,
                        extraction_payload=extraction_payload,
                        extraction_summary=extraction_summary,
                        injected_block=injected_block,
                        reason="Vision extraction completed successfully and markdown was enriched.",
                    )
                )

            except VisionExtractionError:
                failures += 1
                extraction_records.append(
                    VisionExtractionRecord(
                        asset_id=asset.asset_id,
                        classification=asset.classification,
                        status=VisionExtractionStatus.FAILED,
                        priority_rank=priority_rank,
                        extraction_payload=None,
                        extraction_summary=None,
                        injected_block=None,
                        reason="Vision extraction failed validation.",
                    )
                )
                warnings.append(
                    StageWarning(
                        code="VISION_EXTRACTION_FAILED",
                        message="A vision-eligible asset failed extraction or payload validation.",
                        details={"asset_id": asset.asset_id},
                    )
                )

        extraction_duration_ms = (perf_counter() - extraction_start) * 1000

        persistence_start = perf_counter()
        vision_enriched_markdown_artifact = await self._persist_text_artifact(
            document_id=request.document_id,
            relative_blob_path="markdown/vision_enriched.md",
            text=vision_enriched_markdown,
            content_type="text/markdown",
        )
        extraction_manifest_artifact = await self._persist_json_artifact(
            document_id=request.document_id,
            relative_blob_path="vision/extractions.json",
            payload={"records": [record.model_dump(mode="json") for record in extraction_records]},
        )
        persistence_duration_ms = (perf_counter() - persistence_start) * 1000

        total_duration_ms = (perf_counter() - total_start) * 1000
        metrics = Stage5Metrics(
            total_assets_received=len(request.asset_registry.assets),
            total_vision_eligible_assets=len(eligible_assets),
            total_vision_calls_attempted=attempted_calls,
            total_extractions_completed=completed_extractions,
            total_skipped_by_cap=skipped_by_cap,
            total_failures=failures,
            extraction_duration_ms=round(extraction_duration_ms, 3),
            persistence_duration_ms=round(persistence_duration_ms, 3),
            total_duration_ms=round(total_duration_ms, 3),
        )

        if skipped_by_cap > 0:
            warnings.append(
                StageWarning(
                    code="VISION_CALL_CAP_REACHED",
                    message="One or more vision-eligible assets were skipped because the Stage 5 call cap was reached.",
                    details={"skipped_by_cap": skipped_by_cap, "max_vision_calls": request.max_vision_calls},
                )
            )

        return Stage5Output(
            process_id=request.process_id,
            document_id=request.document_id,
            source_blob=request.source_blob,
            vision_enriched_markdown=vision_enriched_markdown,
            vision_enriched_markdown_artifact=vision_enriched_markdown_artifact,
            extraction_manifest_artifact=extraction_manifest_artifact,
            asset_registry=request.asset_registry,
            hyperlink_registry=request.hyperlink_registry,
            table_registry=request.table_registry,
            parse_quality_report=request.parse_quality_report,
            handled_candidates=request.handled_candidates,
            extraction_records=extraction_records,
            warnings=warnings,
            metrics=metrics,
        )

    def _get_priority_sorted_eligible_assets(self, asset_registry: AssetRegistry) -> list[AssetRecord]:
        """Return vision-eligible assets sorted by locked Stage 5 priority order."""
        eligible_assets = [
            asset
            for asset in asset_registry.assets
            if asset.classification in self._PRIORITY_ORDER
        ]
        return sorted(
            eligible_assets,
            key=lambda asset: (self._PRIORITY_ORDER[asset.classification], asset.occurrence_index),
        )

    def _validate_extraction_payload(self, *, asset: AssetRecord, payload: dict) -> None:
        """Validate that the vision extractor returned a usable JSON payload."""
        if not isinstance(payload, dict) or not payload:
            raise VisionExtractionError(
                "Vision extractor returned an empty or invalid payload.",
                context={"asset_id": asset.asset_id},
            )

    def _build_deterministic_summary(self, extraction_payload: dict) -> str:
        """Create a deterministic summary from extracted JSON payload."""
        flattened_parts: list[str] = []

        for key, value in extraction_payload.items():
            if isinstance(value, list):
                flattened_parts.append(f"{key}: {', '.join(str(item) for item in value[:5])}")
            elif isinstance(value, dict):
                flattened_parts.append(f"{key}: {json.dumps(value, ensure_ascii=False, sort_keys=True)}")
            else:
                flattened_parts.append(f"{key}: {value}")

        summary = " | ".join(part.strip() for part in flattened_parts if part.strip()).strip()
        if len(summary) <= 240:
            return summary

        return summary[:237].rstrip() + "..."

    def _build_injected_block(
        self,
        *,
        asset: AssetRecord,
        extraction_payload: dict,
        extraction_summary: str,
    ) -> str:
        """Build the canonical injected [VISION_EXTRACTED: ...] block."""
        block_payload = {
            "asset_id": asset.asset_id,
            "classification": asset.classification.value,
            "summary": extraction_summary,
            "payload": extraction_payload,
        }
        return f"[VISION_EXTRACTED:{json.dumps(block_payload, ensure_ascii=False, sort_keys=True)}]"

    def _inject_after_placeholder(
        self,
        *,
        markdown_text: str,
        placeholder: str,
        injected_block: str,
    ) -> tuple[str, bool]:
        """
        Inject the [VISION_EXTRACTED: ...] block immediately after the first
        matching placeholder occurrence.
        """
        if placeholder not in markdown_text:
            return markdown_text, False

        enriched_markdown = markdown_text.replace(
            placeholder,
            f"{placeholder}\n\n{injected_block}",
            1,
        )
        return enriched_markdown, True

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
                "Failed to persist Stage 5 vision extraction artifact to Azure Blob Storage.",
                context={"document_id": document_id, "blob_path": blob_path},
            ) from exc
