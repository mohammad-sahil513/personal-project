"""
Semantic Kernel Azure OpenAI structured adapter for the Template compiler.

This adapter is a thin compatibility wrapper over the shared infrastructure
adapter in `backend.infrastructure.ai_clients.sk_unified_adapter`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from dotenv import load_dotenv
from backend.core.config import get_settings
from backend.infrastructure.ai_clients.sk_unified_adapter import (
    AzureSemanticKernelTextAdapter,
    AzureDeploymentConfig as UnifiedDeploymentConfig,
)
load_dotenv()

@dataclass(frozen=True, slots=True)
class AzureDeploymentConfig:
    """Configuration for one Azure OpenAI deployment alias."""

    alias: str
    deployment_name: str


class AzureSemanticKernelStructuredAdapter:
    """
    Semantic-Kernel-backed structured adapter for Azure OpenAI chat completion.

    This adapter is suitable for:
    - AICompiler
    - CorrectionLoop

    It expects the model to return a JSON object only.
    """

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        api_key: str | None = None,
        api_version: str | None = None,
        deployments: list[AzureDeploymentConfig | dict[str, str] | object] | None = None,
        default_deployment_alias: str = "gpt5mini",
        instruction_role: str = "system",
    ) -> None:
        settings = get_settings()
        configured_deployments = deployments or [
            AzureDeploymentConfig(alias="gpt5mini", deployment_name="gpt-5-mini"),
            AzureDeploymentConfig(alias="gpt5", deployment_name="gpt-5"),
        ]
        normalized_deployments = [
            self._normalize_deployment(item)
            for item in configured_deployments
        ]
        self._instruction_role = instruction_role
        self._adapter = AzureSemanticKernelTextAdapter(
            settings=settings,
            endpoint=endpoint or settings.azure_openai_endpoint,
            api_key=api_key or settings.azure_openai_api_key,
            api_version=api_version or settings.azure_openai_api_version,
            deployments=[
                UnifiedDeploymentConfig(
                    alias=item.alias,
                    deployment_name=item.deployment_name,
                )
                for item in normalized_deployments
            ],
            default_deployment_alias=default_deployment_alias,
        )

    def invoke_structured(
        self,
        *,
        prompt_template: str,
        input_variables: dict[str, Any],
        execution_hints: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Invoke Azure OpenAI through Semantic Kernel and return a JSON object.
        """
        hints = execution_hints or {}
        return self._adapter.invoke_json(
            prompt_template=prompt_template,
            input_variables=input_variables,
            model_preference=(
                hints.get("model_preference")
                if isinstance(hints.get("model_preference"), str)
                else None
            ),
            reasoning_effort=(
                hints.get("reasoning_effort")
                if isinstance(hints.get("reasoning_effort"), str)
                else None
            ),
            verbosity=(
                hints.get("verbosity")
                if isinstance(hints.get("verbosity"), str)
                else None
            ),
            response_token_budget=(
                hints.get("response_token_budget")
                if isinstance(hints.get("response_token_budget"), int)
                else None
            ),
            instruction_role=self._instruction_role,
        )

    def _normalize_deployment(
        self,
        item: AzureDeploymentConfig | dict[str, str] | object,
    ) -> AzureDeploymentConfig:
        """
        Normalize one deployment entry into AzureDeploymentConfig.

        Accepted inputs:
        - AzureDeploymentConfig
        - {"alias": "...", "deployment_name": "..."}
        - object with `.alias` and `.deployment_name` attributes
        """
        if isinstance(item, AzureDeploymentConfig):
            alias = item.alias
            deployment_name = item.deployment_name
        elif isinstance(item, dict):
            alias = item.get("alias")
            deployment_name = item.get("deployment_name")
        else:
            alias = getattr(item, "alias", None)
            deployment_name = getattr(item, "deployment_name", None)

        alias_str = str(alias) if alias is not None else ""
        deployment_name_str = str(deployment_name) if deployment_name is not None else ""

        if not alias_str.strip():
            raise ValueError(f"Invalid Azure deployment config alias: {item!r}")
        if not deployment_name_str.strip():
            raise ValueError(f"Invalid Azure deployment config deployment_name: {item!r}")

        return AzureDeploymentConfig(
            alias=alias_str.strip().lower(),
            deployment_name=deployment_name_str.strip(),
        )