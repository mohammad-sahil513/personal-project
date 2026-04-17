"""
PII service for Stage 3.

This service performs:
- candidate detection through a pluggable detector interface
- contextual MASK / KEEP decisioning through a pluggable classifier interface
- selective masking of confirmed PII
- secure persistence of the reversible mapping to blob storage

Important design note:
- the final production classifier can be backed by Semantic Kernel + Azure OpenAI
  (e.g. gpt5mini), but the business logic remains here in the service layer.
"""

from __future__ import annotations

import json
import re
from time import perf_counter
from typing import Protocol

from backend.modules.ingestion.contracts.stage_1_contracts import BlobArtifactReference, StageWarning
from backend.modules.ingestion.contracts.stage_3_contracts import (
    ContextualPiiDecision,
    MaskedCandidateRecord,
    PiiCandidate,
    PiiDecisionAction,
    PiiEntityType,
    Stage3Input,
    Stage3Metrics,
    Stage3Output,
)
from backend.modules.ingestion.exceptions import BlobStorageError, PiiProcessingError


class PiiCandidateDetectorProtocol(Protocol):
    """Minimal detector interface for Stage 3 candidate detection."""

    async def detect_candidates(self, *, text: str) -> list[PiiCandidate]:
        """Return ordered Stage 3 PII candidates from the input text."""
        ...


class PiiClassifierProtocol(Protocol):
    """Minimal classifier interface for Stage 3 contextual MASK / KEEP decisions."""

    async def classify_candidates(
        self,
        *,
        text: str,
        candidates: list[PiiCandidate],
        system_email_allowlist: list[str],
    ) -> list[ContextualPiiDecision]:
        """Return one contextual decision for each candidate."""
        ...


class BlobPersistenceClientProtocol(Protocol):
    """Minimal blob persistence contract used by Stage 3."""

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


class RegexPiiCandidateDetector:
    """
    Deterministic fallback candidate detector for Stage 3.

    This keeps the vertical slice runnable and testable without requiring
    a production Presidio integration immediately. A real Presidio-backed
    implementation can later replace this class behind the same interface.
    """

    _EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
    _PHONE_PATTERN = re.compile(r"\b(?:\+?\d[\d\s\-()]{7,}\d)\b")

    async def detect_candidates(self, *, text: str) -> list[PiiCandidate]:
        """Detect email and phone-number candidates in a deterministic way."""
        candidates: list[PiiCandidate] = []
        candidate_index = 1

        for entity_type, pattern in (
            (PiiEntityType.EMAIL_ADDRESS, self._EMAIL_PATTERN),
            (PiiEntityType.PHONE_NUMBER, self._PHONE_PATTERN),
        ):
            for match in pattern.finditer(text):
                candidates.append(
                    PiiCandidate(
                        candidate_id=f"candidate_{candidate_index:03d}",
                        entity_type=entity_type,
                        matched_text=match.group(0),
                        start_char=match.start(),
                        end_char=match.end(),
                    )
                )
                candidate_index += 1

        candidates.sort(key=lambda candidate: candidate.start_char)
        return candidates


class RuleBasedPiiClassifier:
    """
    Deterministic fallback classifier for Stage 3.

    This is not the final production path; it simply provides a clean,
    test-friendly implementation behind the same interface that a future
    Semantic Kernel + Azure OpenAI classifier will use.
    """

    _SERVICE_EMAIL_PREFIXES = (
        "noreply@",
        "no-reply@",
        "donotreply@",
        "do-not-reply@",
        "support@",
        "alerts@",
        "system@",
        "admin@",
    )

    async def classify_candidates(
        self,
        *,
        text: str,
        candidates: list[PiiCandidate],
        system_email_allowlist: list[str],
    ) -> list[ContextualPiiDecision]:
        """Classify candidates using simple allowlist / entity-type rules."""
        normalized_allowlist = {value.strip().lower() for value in system_email_allowlist}
        decisions: list[ContextualPiiDecision] = []

        for candidate in candidates:
            matched_value = candidate.matched_text.strip()
            normalized_value = matched_value.lower()

            if candidate.entity_type == PiiEntityType.EMAIL_ADDRESS:
                if (
                    normalized_value in normalized_allowlist
                    or normalized_value.startswith(self._SERVICE_EMAIL_PREFIXES)
                ):
                    decisions.append(
                        ContextualPiiDecision(
                            candidate_id=candidate.candidate_id,
                            entity_type=candidate.entity_type,
                            action=PiiDecisionAction.KEEP,
                            reason="Service/system email preserved by allowlist or deterministic rule.",
                        )
                    )
                    continue

            decisions.append(
                ContextualPiiDecision(
                    candidate_id=candidate.candidate_id,
                    entity_type=candidate.entity_type,
                    action=PiiDecisionAction.MASK,
                    reason="Candidate treated as personal PII and should be masked.",
                )
            )

        return decisions


class PiiService:
    """Service that executes Stage 3 PII detection and selective masking."""

    def __init__(
        self,
        *,
        candidate_detector: PiiCandidateDetectorProtocol,
        classifier: PiiClassifierProtocol,
        blob_client: BlobPersistenceClientProtocol,
        blob_container_name: str,
        blob_root_prefix: str = "sahil_storage/",
    ) -> None:
        self._candidate_detector = candidate_detector
        self._classifier = classifier
        self._blob_client = blob_client
        self._blob_container_name = blob_container_name
        self._blob_root_prefix = blob_root_prefix.rstrip("/") + "/"

    async def process_pii(self, request: Stage3Input) -> Stage3Output:
        """
        Execute Stage 3 selective masking.

        If `pii_enabled` is False, the service returns the original enriched markdown
        unchanged and skips secure-mapping persistence.
        """
        total_start = perf_counter()

        if not request.pii_enabled:
            metrics = Stage3Metrics(
                total_candidates_detected=0,
                total_candidates_masked=0,
                total_candidates_kept=0,
                detection_duration_ms=0.0,
                classification_duration_ms=0.0,
                masking_duration_ms=0.0,
                persistence_duration_ms=0.0,
                total_duration_ms=0.0,
            )
            return Stage3Output(
                process_id=request.process_id,
                document_id=request.document_id,
                source_blob=request.source_blob,
                masked_markdown=request.enriched_markdown,
                masked_markdown_artifact=request.enriched_markdown_artifact,
                secure_mapping_artifact=None,
                asset_registry=request.asset_registry,
                hyperlink_registry=request.hyperlink_registry,
                table_registry=request.table_registry,
                parse_quality_report=request.parse_quality_report,
                handled_candidates=[],
                warnings=list(request.prior_warnings),
                metrics=metrics,
            )

        detection_start = perf_counter()
        candidates = await self._candidate_detector.detect_candidates(text=request.enriched_markdown)
        detection_duration_ms = (perf_counter() - detection_start) * 1000

        classification_start = perf_counter()
        decisions = await self._classifier.classify_candidates(
            text=request.enriched_markdown,
            candidates=candidates,
            system_email_allowlist=request.system_email_allowlist,
        )
        classification_duration_ms = (perf_counter() - classification_start) * 1000

        self._validate_candidate_decision_alignment(candidates=candidates, decisions=decisions)

        masking_start = perf_counter()
        masked_markdown, secure_mapping_entries, handled_candidates = self._apply_selective_masking(
            text=request.enriched_markdown,
            candidates=candidates,
            decisions=decisions,
        )
        masking_duration_ms = (perf_counter() - masking_start) * 1000

        persistence_start = perf_counter()
        masked_markdown_artifact = await self._persist_text_artifact(
            document_id=request.document_id,
            relative_blob_path="markdown/masked.md",
            text=masked_markdown,
            content_type="text/markdown",
        )

        secure_mapping_artifact = None
        if secure_mapping_entries:
            secure_mapping_artifact = await self._persist_json_artifact(
                document_id=request.document_id,
                relative_blob_path="pii/mapping.json",
                payload={"entries": secure_mapping_entries},
            )
        persistence_duration_ms = (perf_counter() - persistence_start) * 1000

        total_duration_ms = (perf_counter() - total_start) * 1000
        masked_count = sum(1 for record in handled_candidates if record.action == PiiDecisionAction.MASK)
        kept_count = sum(1 for record in handled_candidates if record.action == PiiDecisionAction.KEEP)

        metrics = Stage3Metrics(
            total_candidates_detected=len(candidates),
            total_candidates_masked=masked_count,
            total_candidates_kept=kept_count,
            detection_duration_ms=round(detection_duration_ms, 3),
            classification_duration_ms=round(classification_duration_ms, 3),
            masking_duration_ms=round(masking_duration_ms, 3),
            persistence_duration_ms=round(persistence_duration_ms, 3),
            total_duration_ms=round(total_duration_ms, 3),
        )

        warnings = list(request.prior_warnings)
        if kept_count > 0:
            warnings.append(
                StageWarning(
                    code="PII_CANDIDATES_KEPT",
                    message="One or more detected PII candidates were intentionally preserved after contextual classification.",
                    details={"kept_candidate_count": kept_count},
                )
            )

        return Stage3Output(
            process_id=request.process_id,
            document_id=request.document_id,
            source_blob=request.source_blob,
            masked_markdown=masked_markdown,
            masked_markdown_artifact=masked_markdown_artifact,
            secure_mapping_artifact=secure_mapping_artifact,
            asset_registry=request.asset_registry,
            hyperlink_registry=request.hyperlink_registry,
            table_registry=request.table_registry,
            parse_quality_report=request.parse_quality_report,
            handled_candidates=handled_candidates,
            warnings=warnings,
            metrics=metrics,
        )

    def _validate_candidate_decision_alignment(
        self,
        *,
        candidates: list[PiiCandidate],
        decisions: list[ContextualPiiDecision],
    ) -> None:
        """Ensure the classifier returned exactly one decision per candidate."""
        candidate_ids = [candidate.candidate_id for candidate in candidates]
        decision_ids = [decision.candidate_id for decision in decisions]

        if len(candidate_ids) != len(decision_ids):
            raise PiiProcessingError(
                "Candidate count and decision count do not match.",
                context={
                    "candidate_count": len(candidate_ids),
                    "decision_count": len(decision_ids),
                },
            )

        if sorted(candidate_ids) != sorted(decision_ids):
            raise PiiProcessingError(
                "Classifier decisions do not align with detected candidate IDs.",
                context={
                    "candidate_ids": candidate_ids,
                    "decision_ids": decision_ids,
                },
            )

    def _apply_selective_masking(
        self,
        *,
        text: str,
        candidates: list[PiiCandidate],
        decisions: list[ContextualPiiDecision],
    ) -> tuple[str, list[dict[str, str]], list[MaskedCandidateRecord]]:
        """
        Apply selective masking only to candidates classified as MASK.

        Returns:
        - masked markdown
        - secure mapping entries (for blob persistence only)
        - non-sensitive handled-candidate records for Stage 3 output
        """
        decision_by_id = {decision.candidate_id: decision for decision in decisions}
        replacements: list[tuple[int, int, str]] = []
        secure_mapping_entries: list[dict[str, str]] = []
        handled_candidates: list[MaskedCandidateRecord] = []

        placeholder_counters: dict[PiiEntityType, int] = {
            PiiEntityType.EMAIL_ADDRESS: 0,
            PiiEntityType.PHONE_NUMBER: 0,
            PiiEntityType.PERSON_NAME: 0,
        }

        for candidate in candidates:
            decision = decision_by_id[candidate.candidate_id]

            if decision.action == PiiDecisionAction.MASK:
                placeholder_counters[candidate.entity_type] += 1
                placeholder = self._build_placeholder(
                    entity_type=candidate.entity_type,
                    sequence_number=placeholder_counters[candidate.entity_type],
                )

                replacements.append((candidate.start_char, candidate.end_char, placeholder))
                secure_mapping_entries.append(
                    {
                        "candidate_id": candidate.candidate_id,
                        "entity_type": candidate.entity_type.value,
                        "placeholder": placeholder,
                        "original_value": candidate.matched_text,
                    }
                )
                handled_candidates.append(
                    MaskedCandidateRecord(
                        candidate_id=candidate.candidate_id,
                        entity_type=candidate.entity_type,
                        action=decision.action,
                        placeholder=placeholder,
                        reason=decision.reason,
                    )
                )
            else:
                handled_candidates.append(
                    MaskedCandidateRecord(
                        candidate_id=candidate.candidate_id,
                        entity_type=candidate.entity_type,
                        action=decision.action,
                        placeholder=None,
                        reason=decision.reason,
                    )
                )

        masked_text = text
        for start_char, end_char, placeholder in sorted(replacements, key=lambda item: item[0], reverse=True):
            masked_text = masked_text[:start_char] + placeholder + masked_text[end_char:]

        return masked_text, secure_mapping_entries, handled_candidates

    @staticmethod
    def _build_placeholder(*, entity_type: PiiEntityType, sequence_number: int) -> str:
        """Create a deterministic Stage 3 placeholder."""
        entity_suffix_map = {
            PiiEntityType.EMAIL_ADDRESS: "EMAIL",
            PiiEntityType.PHONE_NUMBER: "PHONE",
            PiiEntityType.PERSON_NAME: "NAME",
        }
        return f"[PII_{entity_suffix_map[entity_type]}_{sequence_number:03d}]"

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
                "Failed to persist Stage 3 PII artifact to Azure Blob Storage.",
                context={"document_id": document_id, "blob_path": blob_path},
            ) from exc