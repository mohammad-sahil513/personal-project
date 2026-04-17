"""
Shared pricing registry service for the observability module.

Responsibilities:
- Load a static pricing registry JSON file
- Expose model/service pricing lookup helpers
- Provide a stable shared pricing source for later cost estimation

Important:
- This file is registry-loading only.
- It does NOT estimate cost.
- It does NOT aggregate cost.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from backend.core.logging import get_logger

logger = get_logger(__name__)


class PricingEntry(BaseModel):
    """
    One pricing entry from the registry.

    The schema is intentionally flexible enough for current needs:
    - `unit` describes the billing unit (e.g. "1k_tokens", "request", "image")
    - `input_cost` / `output_cost` support LLM-style pricing
    - `cost` supports single-value service pricing
    - `currency` defaults to USD unless otherwise specified
    """

    model_config = ConfigDict(extra="allow")

    unit: str | None = Field(default=None)
    input_cost: float | None = Field(default=None, ge=0)
    output_cost: float | None = Field(default=None, ge=0)
    cost: float | None = Field(default=None, ge=0)
    currency: str = Field(default="USD")


class PricingRegistry(BaseModel):
    """
    Top-level pricing registry structure.

    Expected top-level keys:
    - models: pricing for LLM/model-style services
    - services: pricing for request/service-style components
    """

    model_config = ConfigDict(extra="allow")

    models: dict[str, PricingEntry] = Field(default_factory=dict)
    services: dict[str, PricingEntry] = Field(default_factory=dict)


class PricingRegistryService:
    """
    Shared pricing registry loader/lookup service.

    Default path:
        backend/config/pricing_registry.json
    """

    def __init__(self, registry_path: str | Path | None = None) -> None:
        default_path = Path(__file__).resolve().parents[3] / "config" / "pricing_registry.json"
        self.registry_path = Path(registry_path) if registry_path is not None else default_path
        self._registry: PricingRegistry | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, *, force_reload: bool = False) -> PricingRegistry:
        """
        Load the pricing registry from disk.

        Uses cached registry unless `force_reload=True`.
        """
        if self._registry is not None and not force_reload:
            return self._registry

        if not self.registry_path.exists():
            raise FileNotFoundError(
                f"Pricing registry file not found: {self.registry_path}"
            )

        try:
            raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON in pricing registry: {self.registry_path}"
            ) from exc

        if not isinstance(raw, dict):
            raise ValueError("Pricing registry root must be a JSON object.")

        registry = PricingRegistry(
            models=self._coerce_entry_map(raw.get("models", {}), group_name="models"),
            services=self._coerce_entry_map(raw.get("services", {}), group_name="services"),
        )
        self._warn_for_placeholder_pricing(registry)

        self._registry = registry
        return registry

    def get_model_pricing(self, model_name: str) -> PricingEntry:
        """
        Return pricing entry for one model/deployment.
        """
        if not model_name or not model_name.strip():
            raise ValueError("model_name cannot be empty.")

        registry = self.load()
        try:
            return registry.models[model_name]
        except KeyError as exc:
            raise KeyError(f"Model pricing not found for '{model_name}'.") from exc

    def get_service_pricing(self, service_name: str) -> PricingEntry:
        """
        Return pricing entry for one named service.
        """
        if not service_name or not service_name.strip():
            raise ValueError("service_name cannot be empty.")

        registry = self.load()
        try:
            return registry.services[service_name]
        except KeyError as exc:
            raise KeyError(f"Service pricing not found for '{service_name}'.") from exc

    def has_model_pricing(self, model_name: str) -> bool:
        """
        Return True when model pricing exists in the registry.
        """
        if not model_name or not model_name.strip():
            return False
        registry = self.load()
        return model_name in registry.models

    def has_service_pricing(self, service_name: str) -> bool:
        """
        Return True when service pricing exists in the registry.
        """
        if not service_name or not service_name.strip():
            return False
        registry = self.load()
        return service_name in registry.services

    def list_models(self) -> list[str]:
        """
        Return sorted model pricing keys.
        """
        registry = self.load()
        return sorted(registry.models.keys())

    def list_services(self) -> list[str]:
        """
        Return sorted service pricing keys.
        """
        registry = self.load()
        return sorted(registry.services.keys())

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _coerce_entry_map(
        self,
        raw_map: Any,
        *,
        group_name: str,
    ) -> dict[str, PricingEntry]:
        """
        Validate and coerce a dict of pricing entries.
        """
        if raw_map is None:
            return {}

        if not isinstance(raw_map, dict):
            raise ValueError(f"Pricing registry '{group_name}' must be a JSON object.")

        result: dict[str, PricingEntry] = {}
        for key, value in raw_map.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError(f"Pricing registry '{group_name}' contains an invalid empty key.")
            if not isinstance(value, dict):
                raise ValueError(
                    f"Pricing registry '{group_name}.{key}' must be a JSON object."
                )
            result[key] = PricingEntry(**value)

        return result

    def _warn_for_placeholder_pricing(self, registry: PricingRegistry) -> None:
        placeholder_models: list[str] = []
        for model_name, entry in registry.models.items():
            if (entry.input_cost or 0.0) == 0.0 and (entry.output_cost or 0.0) == 0.0:
                placeholder_models.append(model_name)
        placeholder_services: list[str] = []
        for service_name, entry in registry.services.items():
            if (entry.cost or 0.0) == 0.0:
                placeholder_services.append(service_name)
        if placeholder_models or placeholder_services:
            logger.warning(
                "Pricing registry contains placeholder values",
                extra={
                    "placeholder_models": placeholder_models,
                    "placeholder_services": placeholder_services,
                    "registry_path": str(self.registry_path),
                },
            )