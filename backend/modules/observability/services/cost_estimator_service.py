"""
Shared cost estimator service for the observability module.

Responsibilities:
- Estimate token-based LLM/model costs using the pricing registry
- Estimate request/unit-based service costs using the pricing registry
- Provide reusable cost-estimation helpers for Generation and later modules

Important:
- This file is estimation-only.
- It does NOT aggregate cost across sections/documents.
- It does NOT emit logs.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.modules.observability.services.pricing_registry_service import (
    PricingEntry,
    PricingRegistryService,
)


class CostEstimate(BaseModel):
    """
    One cost-estimation result.

    `amount` is the total estimated amount in the pricing-entry currency.
    """

    model_config = ConfigDict(extra="forbid")

    category: str = Field(description="Logical cost category, e.g. llm_generation or service_request.")
    name: str = Field(description="Model/service name used for the estimate.")
    unit: str | None = Field(default=None, description="Billing unit used for the estimate.")
    amount: float = Field(ge=0, description="Estimated cost amount.")
    currency: str = Field(default="USD")
    input_units: float | None = Field(default=None, ge=0)
    output_units: float | None = Field(default=None, ge=0)
    metadata: dict[str, object] = Field(default_factory=dict)


class CostEstimatorService:
    """
    Shared estimator for token-based and request-based costs.

    Supported pricing patterns:
    - token-style models using:
        unit = "1k_tokens"
        input_cost = ...
        output_cost = ...
    - service-style request pricing using:
        unit = "request" (or any unit label)
        cost = ...
    """

    def __init__(self, pricing_registry_service: PricingRegistryService) -> None:
        self.pricing_registry_service = pricing_registry_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate_llm_cost(
        self,
        *,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        category: str = "llm_generation",
        metadata: dict[str, object] | None = None,
    ) -> CostEstimate:
        """
        Estimate LLM/model cost from token counts.

        Expected pricing entry:
        - unit = "1k_tokens"
        - input_cost and/or output_cost
        """
        if prompt_tokens < 0:
            raise ValueError("prompt_tokens cannot be negative.")
        if completion_tokens < 0:
            raise ValueError("completion_tokens cannot be negative.")

        pricing = self.pricing_registry_service.get_model_pricing(model_name)
        self._validate_llm_pricing(pricing, model_name=model_name)

        input_units = prompt_tokens / 1000.0
        output_units = completion_tokens / 1000.0

        amount = (
            (pricing.input_cost or 0.0) * input_units
            + (pricing.output_cost or 0.0) * output_units
        )

        return CostEstimate(
            category=category,
            name=model_name,
            unit=pricing.unit,
            amount=round(amount, 10),
            currency=pricing.currency,
            input_units=input_units,
            output_units=output_units,
            metadata=metadata or {},
        )

    def estimate_service_cost(
        self,
        *,
        service_name: str,
        units: float = 1.0,
        category: str = "service_request",
        metadata: dict[str, object] | None = None,
    ) -> CostEstimate:
        """
        Estimate service/request cost from a unit count.

        Expected pricing entry:
        - unit = any service unit label (e.g. request)
        - cost = single-unit cost
        """
        if units < 0:
            raise ValueError("units cannot be negative.")

        pricing = self.pricing_registry_service.get_service_pricing(service_name)
        self._validate_service_pricing(pricing, service_name=service_name)

        amount = (pricing.cost or 0.0) * units

        return CostEstimate(
            category=category,
            name=service_name,
            unit=pricing.unit,
            amount=round(amount, 10),
            currency=pricing.currency,
            input_units=units,
            output_units=None,
            metadata=metadata or {},
        )

    def estimate_generation_section_cost(
        self,
        *,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        section_id: str | None = None,
        strategy: str | None = None,
    ) -> CostEstimate:
        """
        Convenience wrapper for Generation section LLM cost.
        """
        metadata: dict[str, object] = {}
        if section_id is not None:
            metadata["section_id"] = section_id
        if strategy is not None:
            metadata["strategy"] = strategy

        return self.estimate_llm_cost(
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            category="generation_section",
            metadata=metadata,
        )

    def estimate_diagram_section_cost(
        self,
        *,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        section_id: str | None = None,
    ) -> CostEstimate:
        """
        Convenience wrapper for diagram-generation LLM cost.
        """
        metadata: dict[str, object] = {}
        if section_id is not None:
            metadata["section_id"] = section_id

        return self.estimate_llm_cost(
            model_name=model_name,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            category="diagram_section",
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _validate_llm_pricing(self, pricing: PricingEntry, *, model_name: str) -> None:
        """
        Validate a model pricing entry for token-based estimation.
        """
        if pricing.unit != "1k_tokens":
            raise ValueError(
                f"Model pricing for '{model_name}' must use unit='1k_tokens' for LLM estimation."
            )

        if pricing.input_cost is None and pricing.output_cost is None:
            raise ValueError(
                f"Model pricing for '{model_name}' must define input_cost and/or output_cost."
            )

    def _validate_service_pricing(self, pricing: PricingEntry, *, service_name: str) -> None:
        """
        Validate a service pricing entry for request/unit-based estimation.
        """
        if pricing.cost is None:
            raise ValueError(
                f"Service pricing for '{service_name}' must define cost."
            )