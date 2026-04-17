from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any, Literal, cast
from backend.core.config import Settings, get_settings

from semantic_kernel.connectors.ai.open_ai import (
    AzureChatCompletion,
    AzureChatPromptExecutionSettings,
)
from semantic_kernel.contents import ChatHistory


@dataclass(frozen=True, slots=True)
class AzureDeploymentConfig:
    alias: str
    deployment_name: str


class AzureSemanticKernelTextAdapter:
    """
    Unified Semantic Kernel text adapter for GPT-5 family calls.

    Notes:
    - Does not use temperature or max_tokens.
    - Supports reasoning_effort and response_token_budget (mapped to max_completion_tokens).
    - Safe to call from synchronous code even if an event loop is already running.
    """

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        endpoint: str | None = None,
        api_key: str | None = None,
        api_version: str | None = None,
        deployments: list[AzureDeploymentConfig | dict[str, str] | object] | None = None,
        default_deployment_alias: str = "gpt5mini",
    ) -> None:
        self._settings = settings or get_settings()
        self._endpoint = endpoint or self._settings.azure_openai_endpoint
        self._api_key = api_key or self._settings.azure_openai_api_key
        self._api_version = (
            api_version
            or self._settings.azure_openai_api_version
        )

        if not self._endpoint:
            raise ValueError("AZURE_OPENAI_ENDPOINT is required.")
        if not self._api_key:
            raise ValueError("AZURE_OPENAI_API_KEY is required.")

        configured_deployments = deployments or self._deployments_from_env()
        normalized = [self._normalize_deployment(item) for item in configured_deployments]
        self._deployment_by_alias = {item.alias: item for item in normalized}
        self._deployment_by_name = {item.deployment_name: item for item in normalized}

        normalized_default_alias = self._normalize_alias(default_deployment_alias)
        if normalized_default_alias not in self._deployment_by_alias:
            raise ValueError(
                "Default deployment alias "
                f"`{default_deployment_alias}` is not configured. "
                f"Configured aliases: {sorted(self._deployment_by_alias.keys())}"
            )
        self._default_deployment_alias = normalized_default_alias
        self._service_cache: dict[str, AzureChatCompletion] = {}

    def invoke_text(
        self,
        *,
        prompt_text: str,
        model_preference: str | None = None,
        reasoning_effort: str | None = None,
        verbosity: str | None = None,
        response_token_budget: int | None = None,
    ) -> dict[str, Any]:
        deployment_alias = self._select_deployment_alias(model_preference)
        service = self._get_service(deployment_alias)

        settings = AzureChatPromptExecutionSettings(
            service_id=deployment_alias,
            reasoning_effort=self._coerce_reasoning_effort(reasoning_effort),
            max_completion_tokens=self._coerce_response_budget(response_token_budget),
        )

        history = ChatHistory()
        system_message = "Return plain text only. Do not use markdown fences."
        if isinstance(verbosity, str) and verbosity.strip():
            system_message = f"{system_message}\nTarget response verbosity: {verbosity.strip()}."
        history.add_system_message(system_message)
        history.add_user_message(prompt_text.strip())

        response = self._run_async_blocking(
            service.get_chat_message_content(chat_history=history, settings=settings)
        )
        content = getattr(response, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Azure Semantic Kernel returned an empty/non-text response.")

        return {
            "text": content.strip(),
            "model": self._deployment_by_alias[deployment_alias].deployment_name,
            "deployment_alias": deployment_alias,
            "usage": self._extract_usage(response),
        }

    def invoke_json(
        self,
        *,
        prompt_template: str,
        input_variables: dict[str, Any],
        model_preference: str | None = None,
        reasoning_effort: str | None = None,
        verbosity: str | None = None,
        response_token_budget: int | None = None,
        instruction_role: str = "system",
    ) -> dict[str, Any]:
        deployment_alias = self._select_deployment_alias(model_preference)
        service = self._get_service(deployment_alias)

        settings = AzureChatPromptExecutionSettings(
            service_id=deployment_alias,
            response_format={"type": "json_object"},
            reasoning_effort=self._coerce_reasoning_effort(reasoning_effort),
            max_completion_tokens=self._coerce_response_budget(response_token_budget),
        )

        system_parts = [
            prompt_template.strip(),
            "Return only a valid JSON object. Do not include markdown fences or prose.",
        ]
        if isinstance(verbosity, str) and verbosity.strip():
            system_parts.append(f"Target response verbosity: {verbosity.strip()}.")
        system_message = "\n\n".join(system_parts)

        history = ChatHistory()
        if instruction_role == "developer":
            history.add_system_message(f"[DEVELOPER INSTRUCTION]\n{system_message}")
        else:
            history.add_system_message(system_message)
        history.add_user_message(json_dumps_pretty(input_variables))

        response = self._run_async_blocking(
            service.get_chat_message_content(chat_history=history, settings=settings)
        )
        content = getattr(response, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise ValueError("Azure Semantic Kernel returned an empty/non-text response.")

        try:
            return cast(dict[str, Any], json_loads_strict(content))
        except Exception as exc:
            raise ValueError(
                "Azure Semantic Kernel expected JSON-only output but received invalid JSON."
            ) from exc

    def _deployments_from_env(self) -> list[AzureDeploymentConfig]:
        chat_deployment = (self._settings.azure_openai_chat_deployment or "").strip()
        reasoning_deployment = (self._settings.azure_openai_reasoning_deployment or "").strip()
        fallback = chat_deployment or reasoning_deployment
        if not fallback:
            raise ValueError(
                "Missing Azure deployment configuration. Set AZURE_OPENAI_CHAT_DEPLOYMENT "
                "or AZURE_OPENAI_REASONING_DEPLOYMENT."
            )
        return [
            AzureDeploymentConfig(alias="gpt5mini", deployment_name=chat_deployment or fallback),
            AzureDeploymentConfig(alias="gpt5", deployment_name=reasoning_deployment or fallback),
        ]

    def _select_deployment_alias(self, model_preference: str | None) -> str:
        if isinstance(model_preference, str) and model_preference.strip():
            normalized = self._normalize_alias(model_preference)
            if normalized in self._deployment_by_alias:
                return normalized
            matched_by_name = self._deployment_by_name.get(model_preference.strip())
            if matched_by_name is not None:
                return matched_by_name.alias
        return self._default_deployment_alias

    def _get_service(self, deployment_alias: str) -> AzureChatCompletion:
        normalized_alias = self._normalize_alias(deployment_alias)
        if normalized_alias in self._service_cache:
            return self._service_cache[normalized_alias]

        deployment = self._deployment_by_alias[normalized_alias]
        service = AzureChatCompletion(
            service_id=deployment.alias,
            api_key=self._api_key,
            deployment_name=deployment.deployment_name,
            endpoint=self._endpoint,
            api_version=self._api_version,
        )
        self._service_cache[normalized_alias] = service
        return service

    @staticmethod
    def _normalize_alias(value: str) -> str:
        return value.strip().lower()

    def _normalize_deployment(
        self,
        item: AzureDeploymentConfig | dict[str, str] | object,
    ) -> AzureDeploymentConfig:
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
            raise ValueError(f"Invalid deployment alias: {item!r}")
        if not deployment_name_str.strip():
            raise ValueError(f"Invalid deployment_name: {item!r}")

        return AzureDeploymentConfig(
            alias=self._normalize_alias(alias_str),
            deployment_name=deployment_name_str.strip(),
        )

    @staticmethod
    def _coerce_reasoning_effort(value: str | None) -> Literal["low", "medium", "high"] | None:
        if value in {"low", "medium", "high"}:
            return cast(Literal["low", "medium", "high"], value)
        return None

    @staticmethod
    def _coerce_response_budget(value: int | None) -> int | None:
        if isinstance(value, int) and value > 0:
            return value
        return None

    @staticmethod
    def _run_async_blocking(coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        outcome: dict[str, Any] = {}

        def _runner() -> None:
            try:
                outcome["result"] = asyncio.run(coro)
            except Exception as exc:  # pragma: no cover
                outcome["error"] = exc

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()

        if "error" in outcome:
            raise outcome["error"]
        return outcome["result"]

    @staticmethod
    def _extract_usage(response: Any) -> dict[str, int]:
        usage = getattr(response, "usage", None)
        if usage is None:
            inner_content = getattr(response, "inner_content", None)
            usage = getattr(inner_content, "usage", None)

        if usage is None:
            return {}

        if isinstance(usage, dict):
            prompt_tokens = usage.get("prompt_tokens")
            completion_tokens = usage.get("completion_tokens")
            total_tokens = usage.get("total_tokens")
        else:
            prompt_tokens = getattr(usage, "prompt_tokens", None)
            completion_tokens = getattr(usage, "completion_tokens", None)
            total_tokens = getattr(usage, "total_tokens", None)

        result: dict[str, int] = {}
        if isinstance(prompt_tokens, int) and prompt_tokens >= 0:
            result["prompt_tokens"] = prompt_tokens
        if isinstance(completion_tokens, int) and completion_tokens >= 0:
            result["completion_tokens"] = completion_tokens
        if isinstance(total_tokens, int) and total_tokens >= 0:
            result["total_tokens"] = total_tokens
        return result


def json_dumps_pretty(value: dict[str, Any]) -> str:
    import json
    return json.dumps(value, ensure_ascii=False, indent=2)


def json_loads_strict(value: str) -> Any:
    import json
    return json.loads(value)

