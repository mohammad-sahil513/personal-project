"""
Image classification service for Stage 4.

This service performs:
- deterministic pre-filter classification first
- classifier-based classification only for ambiguous assets
- persistence of the updated asset registry for downstream stages

The final production classifier can later be backed by Semantic Kernel +
Azure OpenAI without changing the service or stage contract.
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
    AssetType,
)
from backend.modules.ingestion.contracts.stage_4_contracts import (
    ClassificationSource,
    ImageClassificationDecision,
    Stage4Input,
    Stage4Metrics,
    Stage4Output,
)
from backend.modules.ingestion.exceptions import BlobStorageError, ImageClassificationError


class AmbiguousImageClassifierProtocol(Protocol):
    """Minimal classifier contract for ambiguous image assets."""

    async def classify_assets(
        self,
        *,
        assets: list[AssetRecord],
    ) -> list[ImageClassificationDecision]:
        """Return one decision for each ambiguous image asset."""
        ...


class BlobPersistenceClientProtocol(Protocol):
    """Minimal blob persistence contract used by Stage 4."""

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


class RuleBasedAmbiguousImageClassifier:
    """
    Deterministic fallback classifier for ambiguous assets.

    This keeps Stage 4 runnable and testable before we add a future prompt-based
    adapter in a later substep.
    """

    def classify_from_text(self, asset: AssetRecord) -> tuple[AssetClassification, str]:
        text = self._build_text(asset)

        if any(keyword in text for keyword in ("sequence", "interaction", "swimlane", "lifeline")):
            return AssetClassification.SEQUENCE, "Classified as sequence diagram from descriptive keywords."

        if any(keyword in text for keyword in ("architecture", "component", "deployment", "system design")):
            return AssetClassification.ARCHITECTURE, "Classified as architecture diagram from descriptive keywords."

        if any(keyword in text for keyword in ("flow", "flowchart", "workflow", "process")):
            return AssetClassification.FLOWCHART, "Classified as flowchart from descriptive keywords."

        return AssetClassification.GENERIC_DIAGRAM, "Ambiguous image treated as a generic diagram."

    async def classify_assets(
        self,
        *,
        assets: list[AssetRecord],
    ) -> list[ImageClassificationDecision]:
        decisions: list[ImageClassificationDecision] = []

        for asset in assets:
            classification, reason = self.classify_from_text(asset)
            decisions.append(
                ImageClassificationDecision(
                    asset_id=asset.asset_id,
                    classification=classification,
                    classification_source=ClassificationSource.AMBIGUOUS_CLASSIFIER,
                    reason=reason,
                )
            )

        return decisions

    @staticmethod
    def _build_text(asset: AssetRecord) -> str:
        return " ".join(
            part.strip().lower()
            for part in [
                asset.alt_text or "",
                asset.source_reference or "",
            ]
            if part and part.strip()
        )


class ImageClassificationService:
    """Service that executes Stage 4 image classification."""

    _NON_DIAGRAM_KEYWORDS = (
        "logo",
        "icon",
        "avatar",
        "photo",
        "photograph",
        "screenshot",
        "banner",
        "cover",
    )

    _FLOWCHART_KEYWORDS = ("flow", "flowchart", "workflow", "process")
    _ARCHITECTURE_KEYWORDS = ("architecture", "component", "deployment", "system")
    _SEQUENCE_KEYWORDS = ("sequence", "interaction", "lifeline", "swimlane")

    def __init__(
        self,
        *,
        ambiguous_classifier: AmbiguousImageClassifierProtocol,
        blob_client: BlobPersistenceClientProtocol,
        blob_container_name: str,
        blob_root_prefix: str = "sahil_storage/",
    ) -> None:
        self._ambiguous_classifier = ambiguous_classifier
        self._blob_client = blob_client
        self._blob_container_name = blob_container_name
        self._blob_root_prefix = blob_root_prefix.rstrip("/") + "/"

    async def classify_images(self, request: Stage4Input) -> Stage4Output:
        """Run deterministic pre-filtering and classify only ambiguous image assets."""
        total_start = perf_counter()

        prefilter_start = perf_counter()
        decisions: list[ImageClassificationDecision] = []
        ambiguous_assets: list[AssetRecord] = []

        for asset in request.asset_registry.assets:
            if asset.asset_type != AssetType.IMAGE:
                decisions.append(
                    ImageClassificationDecision(
                        asset_id=asset.asset_id,
                        classification=asset.classification,
                        classification_source=ClassificationSource.SKIPPED_NON_IMAGE,
                        reason="Non-image asset skipped by Stage 4 image classification.",
                    )
                )
                continue

            prefilter_decision = self._deterministic_prefilter(asset)
            if prefilter_decision is None:
                ambiguous_assets.append(asset)
            else:
                decisions.append(prefilter_decision)

        prefilter_duration_ms = (perf_counter() - prefilter_start) * 1000

        classifier_start = perf_counter()
        if ambiguous_assets:
            classifier_decisions = await self._ambiguous_classifier.classify_assets(assets=ambiguous_assets)
            self._validate_ambiguous_decisions(ambiguous_assets=ambiguous_assets, decisions=classifier_decisions)
            decisions.extend(classifier_decisions)
        classifier_duration_ms = (perf_counter() - classifier_start) * 1000

        updated_registry = self._apply_decisions_to_registry(
            asset_registry=request.asset_registry,
            decisions=decisions,
        )

        persistence_start = perf_counter()
        classified_registry_artifact = await self._persist_json_artifact(
            document_id=request.document_id,
            relative_blob_path="assets/assets_classified.json",
            payload=updated_registry.model_dump(mode="json"),
        )
        persistence_duration_ms = (perf_counter() - persistence_start) * 1000

        total_duration_ms = (perf_counter() - total_start) * 1000
        deterministic_count = sum(
            1 for decision in decisions if decision.classification_source == ClassificationSource.DETERMINISTIC_PREFILTER
        )
        ambiguous_count = sum(
            1 for decision in decisions if decision.classification_source == ClassificationSource.AMBIGUOUS_CLASSIFIER
        )
        vision_eligible_count = sum(
            1
            for asset in updated_registry.assets
            if asset.classification
            in {
                AssetClassification.FLOWCHART,
                AssetClassification.ARCHITECTURE,
                AssetClassification.SEQUENCE,
                AssetClassification.GENERIC_DIAGRAM,
            }
        )

        metrics = Stage4Metrics(
            total_assets_received=len(request.asset_registry.assets),
            total_image_assets=sum(1 for asset in request.asset_registry.assets if asset.asset_type == AssetType.IMAGE),
            deterministic_classification_count=deterministic_count,
            ambiguous_classification_count=ambiguous_count,
            total_vision_eligible_assets=vision_eligible_count,
            prefilter_duration_ms=round(prefilter_duration_ms, 3),
            classifier_duration_ms=round(classifier_duration_ms, 3),
            persistence_duration_ms=round(persistence_duration_ms, 3),
            total_duration_ms=round(total_duration_ms, 3),
        )

        warnings = list(request.prior_warnings)
        if ambiguous_assets:
            warnings.append(
                StageWarning(
                    code="AMBIGUOUS_IMAGE_CLASSIFICATION_USED",
                    message="One or more image assets required the ambiguous-classifier path.",
                    details={"ambiguous_asset_count": len(ambiguous_assets)},
                )
            )

        return Stage4Output(
            process_id=request.process_id,
            document_id=request.document_id,
            source_blob=request.source_blob,
            masked_markdown=request.masked_markdown,
            masked_markdown_artifact=request.masked_markdown_artifact,
            secure_mapping_artifact=request.secure_mapping_artifact,
            asset_registry=updated_registry,
            classified_asset_registry_artifact=classified_registry_artifact,
            hyperlink_registry=request.hyperlink_registry,
            table_registry=request.table_registry,
            parse_quality_report=request.parse_quality_report,
            handled_candidates=request.handled_candidates,
            decisions=decisions,
            warnings=warnings,
            metrics=metrics,
        )

    def _deterministic_prefilter(self, asset: AssetRecord) -> ImageClassificationDecision | None:
        """
        Deterministically classify obvious image assets.

        Returns None when the asset remains ambiguous and must go through the
        classifier path.
        """
        text = self._build_text(asset)

        if any(keyword in text for keyword in self._NON_DIAGRAM_KEYWORDS):
            return ImageClassificationDecision(
                asset_id=asset.asset_id,
                classification=AssetClassification.NON_DIAGRAM,
                classification_source=ClassificationSource.DETERMINISTIC_PREFILTER,
                reason="Obvious non-diagram image detected via deterministic pre-filter.",
            )

        if any(keyword in text for keyword in self._FLOWCHART_KEYWORDS):
            return ImageClassificationDecision(
                asset_id=asset.asset_id,
                classification=AssetClassification.FLOWCHART,
                classification_source=ClassificationSource.DETERMINISTIC_PREFILTER,
                reason="Flowchart-like keywords detected via deterministic pre-filter.",
            )

        if any(keyword in text for keyword in self._ARCHITECTURE_KEYWORDS):
            return ImageClassificationDecision(
                asset_id=asset.asset_id,
                classification=AssetClassification.ARCHITECTURE,
                classification_source=ClassificationSource.DETERMINISTIC_PREFILTER,
                reason="Architecture-like keywords detected via deterministic pre-filter.",
            )

        if any(keyword in text for keyword in self._SEQUENCE_KEYWORDS):
            return ImageClassificationDecision(
                asset_id=asset.asset_id,
                classification=AssetClassification.SEQUENCE,
                classification_source=ClassificationSource.DETERMINISTIC_PREFILTER,
                reason="Sequence-diagram-like keywords detected via deterministic pre-filter.",
            )

        return None

    def _validate_ambiguous_decisions(
        self,
        *,
        ambiguous_assets: list[AssetRecord],
        decisions: list[ImageClassificationDecision],
    ) -> None:
        """Ensure the ambiguous classifier returned exactly one decision per ambiguous asset."""
        expected_ids = sorted(asset.asset_id for asset in ambiguous_assets)
        actual_ids = sorted(decision.asset_id for decision in decisions)

        if expected_ids != actual_ids:
            raise ImageClassificationError(
                "Ambiguous image-classifier decisions do not align with the provided asset IDs.",
                context={
                    "expected_ids": expected_ids,
                    "actual_ids": actual_ids,
                },
            )

    def _apply_decisions_to_registry(
        self,
        *,
        asset_registry: AssetRegistry,
        decisions: list[ImageClassificationDecision],
    ) -> AssetRegistry:
        """Return a new asset registry with Stage 4 classifications applied."""
        decision_by_asset_id = {decision.asset_id: decision for decision in decisions}
        updated_assets: list[AssetRecord] = []

        for asset in asset_registry.assets:
            decision = decision_by_asset_id.get(asset.asset_id)
            if decision is None:
                updated_assets.append(asset)
                continue

            updated_assets.append(
                asset.model_copy(update={"classification": decision.classification})
            )

        return AssetRegistry(assets=updated_assets)

    @staticmethod
    def _build_text(asset: AssetRecord) -> str:
        return " ".join(
            part.strip().lower()
            for part in [
                asset.alt_text or "",
                asset.source_reference or "",
            ]
            if part and part.strip()
        )

    async def _persist_json_artifact(
        self,
        *,
        document_id: str,
        relative_blob_path: str,
        payload: dict,
    ) -> BlobArtifactReference:
        blob_path = f"{self._blob_root_prefix}ingestion/{document_id}/{relative_blob_path}"

        try:
            return await self._blob_client.upload_bytes(
                container_name=self._blob_container_name,
                blob_path=blob_path,
                data=json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"),
                content_type="application/json",
                overwrite=True,
            )
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise BlobStorageError(
                "Failed to persist Stage 4 classified asset registry to Azure Blob Storage.",
                context={"document_id": document_id, "blob_path": blob_path},
            ) from exc