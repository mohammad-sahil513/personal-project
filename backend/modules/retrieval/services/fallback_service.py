# backend/modules/retrieval/services/fallback_service.py

from __future__ import annotations

from backend.modules.retrieval.contracts.retrieval_contracts import FallbackPolicy, RetrievalPlan


class FallbackService:
    """
    Enforces bounded fallback behavior.
    """

    @staticmethod
    def can_attempt_fallback(
        *,
        plan: RetrievalPlan,
        attempts_used: int,
    ) -> bool:
        return attempts_used < plan.max_fallback_attempts

    @staticmethod
    def apply_policy(
        *,
        plan: RetrievalPlan,
        reason: str,
    ) -> dict[str, bool | str]:
        """
        Return policy effects without executing search.
        """
        if plan.fallback_policy == FallbackPolicy.ESCALATE_INSUFFICIENT:
            return {"retry": False, "reason": reason}

        if plan.fallback_policy in {
            FallbackPolicy.EXPAND_QUERY,
            FallbackPolicy.PARENT_SECTION,
            FallbackPolicy.BEST_EFFORT,
        }:
            return {"retry": True, "reason": reason}

        return {"retry": False, "reason": reason}