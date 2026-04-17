# backend/modules/retrieval/services/profile_resolver.py

from __future__ import annotations

from typing import Tuple

from backend.modules.retrieval.contracts.retrieval_contracts import (
    FallbackPolicy,
    RetrievalPlan,
    RetrievalRequest,
    RetrievalWarningCode,
)
from backend.modules.retrieval.profiles.retrieval_profiles import get_retrieval_profile


class ProfileResolutionError(ValueError):
    """Raised when retrieval profile resolution fails."""


class RetrievalProfileResolver:
    """
    Resolve a RetrievalRequest into a single executable RetrievalPlan.
    """

    @staticmethod
    def resolve(request: RetrievalRequest) -> Tuple[RetrievalPlan, list[RetrievalWarningCode]]:
        """
        Resolve profile / inline plan and apply overrides.

        Returns:
            (RetrievalPlan, warnings)
        """
        warnings: list[str] = []

        # Step 1: Load base plan
        if request.profile_name:
            try:
                plan = get_retrieval_profile(request.profile_name)
            except KeyError as exc:
                raise ProfileResolutionError(str(exc)) from exc

            if request.inline_plan is not None:
                warnings.append(RetrievalWarningCode.INLINE_PLAN_IGNORED)
        else:
            if request.inline_plan is None:
                raise ProfileResolutionError(
                    "Either profile_name or inline_plan must be provided."
                )
            plan = request.inline_plan.model_copy(deep=True)

        # Step 2: Apply overrides
        if request.fallback_policy_override is not None:
            plan.fallback_policy = request.fallback_policy_override

        if request.min_confidence_override is not None:
            plan.min_confidence = request.min_confidence_override

        # Step 3: Merge filters (request filters override profile defaults)
        if request.filters:
            plan.filters = request.filters

        # Step 4: Final validation
        RetrievalProfileResolver._validate_plan(plan)

        return plan, warnings

    @staticmethod
    def _validate_plan(plan: RetrievalPlan) -> None:
        """
        Final safety checks before search execution.
        """
        if plan.top_k < 1:
            raise ProfileResolutionError("top_k must be >= 1")

        if plan.final_output_top_k < 1:
            raise ProfileResolutionError("final_output_top_k must be >= 1")

        if plan.final_output_top_k > plan.top_k:
            # This is allowed, but usually suspicious
            pass

        if plan.max_fallback_attempts > 1:
            raise ProfileResolutionError("Only one fallback attempt is allowed")

        if not plan.source_enabled and not plan.guideline_enabled:
            raise ProfileResolutionError(
                "At least one retrieval pool must be enabled"
            )