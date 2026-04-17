"""
Semantic Kernel-style classifier adapter for Stage 3 PII processing.

This adapter implements the existing `PiiClassifierProtocol` used by PiiService.
It is designed so that a future production implementation can invoke Semantic
Kernel with Azure OpenAI (for example, the `gpt5mini` deployment) without
changing the Stage 3 business logic.

Key responsibilities:
- load the locked Stage 3 prompt from prompts/ingestion/pii_classification_v1.yaml
- build stable candidate-context payloads
- invoke a pluggable kernel adapter
- parse and validate JSON model output
- return ContextualPiiDecision objects to PiiService
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol
import yaml

from backend.modules.ingestion.contracts.stage_3_contracts import (
    ContextualPiiDecision,
    PiiCandidate,
    PiiClassificationBatchRequest,
    PiiClassificationBatchResponse,
    PiiClassifierCandidateContext,
)
from backend.modules.ingestion.services.pii_service import PiiClassifierProtocol
from backend.modules.ingestion.exceptions import PiiProcessingError


class SemanticKernelPromptExecutorProtocol(Protocol):
    """
    Minimal Semantic Kernel-style prompt execution contract.

    A future infrastructure-backed implementation can wrap Semantic Kernel and
    Azure OpenAI behind this same interface.
    """

    async def invoke_prompt(
        self,
        *,
        prompt_template: str,
        arguments: dict[str, Any],
        service_id: str,
    ) -> str:
        """
        Execute the prompt and return the raw model output as text.

        The `service_id` should map to the Azure OpenAI deployment name used by
        the underlying Semantic Kernel connector.
        """
        ...


class SemanticKernelPiiClassifier(PiiClassifierProtocol):
    """
    Production-ready classifier adapter shape for Stage 3.

    This adapter keeps Stage 3 aligned with the locked architecture:
    - Semantic Kernel remains the orchestration layer
    - Azure OpenAI deployment selection is explicit
    - prompt execution stays outside core Stage 3 business logic
    """

    _FENCED_JSON_PATTERN = re.compile(r"^```(?:json)?\s*(?P<body>.*?)\s*```$", re.DOTALL | re.IGNORECASE)

    def __init__(
        self,
        *,
        prompt_executor: SemanticKernelPromptExecutorProtocol,
        prompt_template_path: str | Path = "prompts/ingestion/pii_classification_v1.yaml",
        deployment_name: str = "gpt5mini",
        prompt_version: str = "pii_classification_v1",
        context_window_chars: int = 120,
    ) -> None:
        self._prompt_executor = prompt_executor
        self._prompt_template_path = Path(prompt_template_path)
        self._deployment_name = deployment_name
        self._prompt_version = prompt_version
        self._context_window_chars = context_window_chars

    async def classify_candidates(
        self,
        *,
        text: str,
        candidates: list[PiiCandidate],
        system_email_allowlist: list[str],
    ) -> list[ContextualPiiDecision]:
        """
        Classify PII candidates through a prompt-based adapter path.

        Returns one ContextualPiiDecision per candidate.
        """
        if not candidates:
            return []

        prompt_template = self._load_prompt_template()
        batch_request = self._build_batch_request(
            text=text,
            candidates=candidates,
            system_email_allowlist=system_email_allowlist,
        )

        request_payload = {
            "document_id": batch_request.document_id,
            "prompt_version": batch_request.prompt_version,
            "deployment_name": batch_request.deployment_name,
            "candidates": [candidate.model_dump(mode="json") for candidate in batch_request.candidates],
        }

        try:
            raw_output = await self._prompt_executor.invoke_prompt(
                prompt_template=prompt_template,
                arguments={
                    "candidate_batch_json": json.dumps(request_payload, ensure_ascii=False, indent=2),
                },
                service_id=self._deployment_name,
            )
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise PiiProcessingError(
                "Stage 3 classifier adapter failed during prompt execution.",
                context={
                    "deployment_name": self._deployment_name,
                    "prompt_version": self._prompt_version,
                },
            ) from exc

        parsed_response = self._parse_model_output(raw_output)
        self._validate_decision_alignment(
            candidates=candidates,
            decisions=parsed_response.decisions,
        )

        return parsed_response.decisions

    def _build_batch_request(
        self,
        *,
        text: str,
        candidates: list[PiiCandidate],
        system_email_allowlist: list[str],
    ) -> PiiClassificationBatchRequest:
        """Build a stable batch request for prompt-based classification."""
        normalized_allowlist = {value.strip().lower() for value in system_email_allowlist}

        contexts: list[PiiClassifierCandidateContext] = []
        for candidate in candidates:
            surrounding_text = self._extract_surrounding_text(
                text=text,
                start_char=candidate.start_char,
                end_char=candidate.end_char,
            )
            contexts.append(
                PiiClassifierCandidateContext(
                    candidate_id=candidate.candidate_id,
                    entity_type=candidate.entity_type,
                    matched_text=candidate.matched_text,
                    surrounding_text=surrounding_text,
                    is_allowlisted_system_value=candidate.matched_text.strip().lower() in normalized_allowlist,
                )
            )

        return PiiClassificationBatchRequest(
            document_id="stage_3_document",
            prompt_version=self._prompt_version,
            deployment_name=self._deployment_name,
            candidates=contexts,
        )

    def _load_prompt_template(self) -> str:
        """Load the locked Stage 3 prompt template from YAML or plain text."""
        try:
            prompt_text = self._prompt_template_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise PiiProcessingError(
                "Stage 3 classifier prompt template could not be found.",
                context={"prompt_template_path": str(self._prompt_template_path)},
            ) from exc

        if not prompt_text:
            raise PiiProcessingError(
                "Stage 3 classifier prompt template is empty.",
                context={"prompt_template_path": str(self._prompt_template_path)},
            )

        if self._prompt_template_path.suffix.lower() in {".yaml", ".yml"}:
            try:
                payload = yaml.safe_load(prompt_text)
            except yaml.YAMLError as exc:
                raise PiiProcessingError(
                    "Stage 3 classifier prompt YAML is invalid.",
                    context={"prompt_template_path": str(self._prompt_template_path)},
                ) from exc

            if not isinstance(payload, dict):
                raise PiiProcessingError(
                    "Stage 3 classifier prompt YAML must be a mapping/object.",
                    context={"prompt_template_path": str(self._prompt_template_path)},
                )

            template = payload.get("prompt_template") or payload.get("template")
            if not isinstance(template, str) or not template.strip():
                raise PiiProcessingError(
                    "Stage 3 classifier prompt YAML must define `prompt_template` or `template`.",
                    context={"prompt_template_path": str(self._prompt_template_path)},
                )
            return template.strip()

        return prompt_text

    def _parse_model_output(self, raw_output: str) -> PiiClassificationBatchResponse:
        """
        Parse raw model output into a validated classification batch response.

        Supported shapes:
        - plain JSON
        - fenced JSON blocks
        """
        cleaned_output = raw_output.strip()
        fenced_match = self._FENCED_JSON_PATTERN.match(cleaned_output)
        if fenced_match:
            cleaned_output = fenced_match.group("body").strip()

        try:
            payload = json.loads(cleaned_output)
        except json.JSONDecodeError as exc:
            raise PiiProcessingError(
                "Stage 3 classifier returned invalid JSON.",
                context={"raw_output": raw_output[:500]},
            ) from exc

        if "deployment_name" not in payload:
            payload["deployment_name"] = self._deployment_name

        try:
            return PiiClassificationBatchResponse.model_validate(payload)
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise PiiProcessingError(
                "Stage 3 classifier JSON did not match the expected response contract.",
                context={"payload": payload},
            ) from exc

    def _validate_decision_alignment(
        self,
        *,
        candidates: list[PiiCandidate],
        decisions: list[ContextualPiiDecision],
    ) -> None:
        """Ensure the prompt-based classifier returned exactly one decision per candidate."""
        candidate_ids = sorted(candidate.candidate_id for candidate in candidates)
        decision_ids = sorted(decision.candidate_id for decision in decisions)

        if candidate_ids != decision_ids:
            raise PiiProcessingError(
                "Stage 3 classifier decisions do not align with the provided candidate IDs.",
                context={
                    "candidate_ids": candidate_ids,
                    "decision_ids": decision_ids,
                    "deployment_name": self._deployment_name,
                },
            )

    def _extract_surrounding_text(
        self,
        *,
        text: str,
        start_char: int,
        end_char: int,
    ) -> str:
        """
        Extract a bounded context window around a matched candidate.

        This makes prompt input deterministic and avoids sending the entire
        document when only local context is needed.
        """
        left_bound = max(0, start_char - self._context_window_chars)
        right_bound = min(len(text), end_char + self._context_window_chars)
        return text[left_bound:right_bound].strip()