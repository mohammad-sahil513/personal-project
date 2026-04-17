# backend/modules/retrieval/services/retrieval_service.py

from __future__ import annotations

import uuid

from backend.modules.retrieval.contracts.retrieval_contracts import (
    RetrievalCostSummary,
    RetrievalDiagnostics,
    RetrievalRequest,
    RetrievalStatus,
    RetrievalWarningCode,
)
from backend.modules.retrieval.services.profile_resolver import RetrievalProfileResolver
from backend.modules.retrieval.services.query_builder import QueryBuilderService
from backend.modules.retrieval.services.vector_search_service import VectorSearchService
from backend.modules.retrieval.services.reranker_service import RerankerService
from backend.modules.retrieval.services.fallback_service import FallbackService
from backend.modules.retrieval.services.evidence_packager import EvidencePackager
from backend.modules.observability.services.cost_aggregation_service import (
    CostAggregationService,
)
from backend.modules.observability.services.cost_estimator_service import (
    CostEstimatorService,
)
from backend.modules.observability.services.logging_service import LoggingService
from backend.modules.observability.services.request_context_service import (
    RequestContextService,
)


class RetrievalService:
    """
    Top-level retrieval orchestrator.

    This is the only entrypoint that downstream generation should call.
    """

    def __init__(
        self,
        *,
        vector_search_service: VectorSearchService,
        logging_service: LoggingService | None = None,
        request_context_service: RequestContextService | None = None,
        cost_estimator_service: CostEstimatorService | None = None,
        cost_aggregation_service: CostAggregationService | None = None,
    ) -> None:
        self._vector_search_service = vector_search_service
        self._request_context_service = request_context_service or RequestContextService()
        self._logging_service = logging_service or LoggingService(
            context_provider=self._request_context_service.get_context_dict
        )
        self._cost_estimator_service = cost_estimator_service
        self._cost_aggregation_service = cost_aggregation_service

    def retrieve(
        self,
        request: RetrievalRequest,
    ):
        self._logging_service.info(
            "retrieval_started",
            retrieval_id=request.retrieval_id,
            profile_name=request.profile_name,
            section_heading=request.section_heading,
        )
        # ------------------------------------------------------------
        # Step 1: Resolve retrieval plan
        # ------------------------------------------------------------
        plan, resolver_warnings = RetrievalProfileResolver.resolve(request)
        self._logging_service.info(
            "retrieval_plan_resolved",
            retrieval_id=request.retrieval_id,
            search_mode=plan.search_mode.value if hasattr(plan.search_mode, "value") else str(plan.search_mode),
            source_enabled=plan.source_enabled,
            guideline_enabled=plan.guideline_enabled,
        )

        # ------------------------------------------------------------
        # Step 2: Build query
        # ------------------------------------------------------------
        query = QueryBuilderService.build(
            request=request,
            plan=plan,
        )
        self._logging_service.info(
            "retrieval_query_built",
            retrieval_id=request.retrieval_id,
            token_count=query.token_count,
            semantic_role_key=query.semantic_role_key,
        )

        # ------------------------------------------------------------
        # Step 3: Execute hierarchical search
        # ------------------------------------------------------------
        hierarchical_result = self._vector_search_service.search(
            query=query,
            plan=plan,
            filters=plan.filters,
        )
        self._logging_service.info(
            "retrieval_search_completed",
            retrieval_id=request.retrieval_id,
            source_candidates=(len(hierarchical_result.source.candidates) if hierarchical_result.source else 0),
            guideline_candidates=(len(hierarchical_result.guideline.candidates) if hierarchical_result.guideline else 0),
            warning_count=len(hierarchical_result.warnings),
        )

        # ------------------------------------------------------------
        # Step 4: Collect candidates
        # ------------------------------------------------------------
        source_candidates = []
        guideline_candidates = []

        if hierarchical_result.source:
            source_candidates = hierarchical_result.source.candidates

        if hierarchical_result.guideline:
            guideline_candidates = hierarchical_result.guideline.candidates

        fallback_used = False
        fallback_attempts = 0

        # ------------------------------------------------------------
        # Step 5: Fallback control (bounded)
        # ------------------------------------------------------------
        if (
            not source_candidates
            and FallbackService.can_attempt_fallback(
                plan=plan,
                attempts_used=fallback_attempts,
            )
        ):
            fallback_attempts += 1
            fallback_used = True

        # ------------------------------------------------------------
        # Step 6: Rerank (SOURCE first)
        # ------------------------------------------------------------
        ranked_candidates = RerankerService.rerank(
            source_candidates=source_candidates,
            guideline_candidates=guideline_candidates,
            plan=plan,
        )
        self._logging_service.info(
            "retrieval_rerank_completed",
            retrieval_id=request.retrieval_id,
            ranked_count=len(ranked_candidates),
        )

        ranked_source = [c for c in ranked_candidates if c.source_role.name == "SOURCE"]
        ranked_guideline = [
            c for c in ranked_candidates if c.source_role.name == "GUIDELINE"
        ]

        # ------------------------------------------------------------
        # Step 7: Package evidence
        # ------------------------------------------------------------
        evidence_bundle_id = f"evb_{uuid.uuid4().hex[:12]}"

        evidence_bundle = EvidencePackager.package(
            evidence_bundle_id=evidence_bundle_id,
            source_candidates=ranked_source,
            guideline_candidates=ranked_guideline,
            fallback_used=fallback_used,
        )

        # ------------------------------------------------------------
        # Step 8: Diagnostics + status
        # ------------------------------------------------------------
        status = (
            RetrievalStatus.OK
            if evidence_bundle.source.facts
            else RetrievalStatus.INSUFFICIENT_EVIDENCE
        )
       
        diagnostic_warnings = [
            *resolver_warnings,
            *hierarchical_result.warnings,
        ]
        if fallback_used and RetrievalWarningCode.FALLBACK_USED not in diagnostic_warnings:
            diagnostic_warnings.append(RetrievalWarningCode.FALLBACK_USED)

        diagnostics = RetrievalDiagnostics(
            retrieval_id=request.retrieval_id,
            status=status,
            final_confidence=evidence_bundle.overall_confidence,
            min_confidence=plan.min_confidence,
            fallback_attempted=fallback_used,
            fallback_policy_used=plan.fallback_policy if fallback_used else None,
            warnings=diagnostic_warnings,
            search_mode=plan.search_mode,
            source_selected_count=len(evidence_bundle.source.facts),
            guideline_selected_count=len(evidence_bundle.guideline.items),
            evidence_bundle_id=evidence_bundle_id,
            cost_summary=self._build_cost_summary(
                request=request,
                query_token_count=query.token_count,
                hierarchical_result=hierarchical_result,
                fallback_used=fallback_used,
            ),
        )
        self._logging_service.info(
            "retrieval_completed",
            retrieval_id=request.retrieval_id,
            status=status.value if hasattr(status, "value") else str(status),
            final_confidence=diagnostics.final_confidence,
            source_selected_count=diagnostics.source_selected_count,
            guideline_selected_count=diagnostics.guideline_selected_count,
            estimated_cost_usd=diagnostics.cost_summary.estimated_cost_usd,
        )

        return evidence_bundle, diagnostics, status

    def _build_cost_summary(
        self,
        *,
        request: RetrievalRequest,
        query_token_count: int,
        hierarchical_result,
        fallback_used: bool,
    ) -> RetrievalCostSummary:
        search_requests_count = 0
        if hierarchical_result.source is not None:
            search_requests_count += 2 if not hierarchical_result.source.used_flat_fallback else 1
        if hierarchical_result.guideline is not None:
            search_requests_count += 2 if not hierarchical_result.guideline.used_flat_fallback else 1
        fallback_search_requests_count = 1 if fallback_used else 0

        estimated_cost_usd = 0.0
        if self._cost_estimator_service is not None:
            try:
                model_name = "text-embedding-3-small"
                embedding_estimate = self._cost_estimator_service.estimate_llm_cost(
                    model_name=model_name,
                    prompt_tokens=query_token_count,
                    completion_tokens=0,
                    category="retrieval_embedding",
                    metadata={"retrieval_id": request.retrieval_id},
                )
                search_estimate = self._cost_estimator_service.estimate_service_cost(
                    service_name="azure_search",
                    units=float(search_requests_count + fallback_search_requests_count),
                    category="retrieval_search",
                    metadata={"retrieval_id": request.retrieval_id},
                )
                estimated_cost_usd = embedding_estimate.amount + search_estimate.amount
                if self._cost_aggregation_service is not None:
                    job_id = request.project_id or request.retrieval_id
                    self._cost_aggregation_service.add_cost_record(
                        job_id=job_id,
                        category="retrieval_embedding",
                        estimate=embedding_estimate,
                        section_id=request.target_section_id,
                    )
                    self._cost_aggregation_service.add_cost_record(
                        job_id=job_id,
                        category="retrieval_search",
                        estimate=search_estimate,
                        section_id=request.target_section_id,
                    )
            except Exception as exc:
                self._logging_service.warning(
                    "retrieval_cost_estimation_failed",
                    retrieval_id=request.retrieval_id,
                    error_message=str(exc),
                )

        return RetrievalCostSummary(
            query_embedding_tokens=query_token_count,
            search_requests_count=search_requests_count,
            fallback_search_requests_count=fallback_search_requests_count,
            estimated_cost_usd=round(estimated_cost_usd, 10),
        )