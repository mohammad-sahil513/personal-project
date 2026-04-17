"""
Centralized backend settings.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.core.constants import (
    API_PREFIX,
    DEFAULT_APP_ENV,
    DEFAULT_APP_NAME,
    DEFAULT_CORS_ORIGINS,
    DEFAULT_HOST,
    DEFAULT_LOG_LEVEL,
    DEFAULT_PORT,
    DEFAULT_STORAGE_ROOT,
    DEFAULT_WORKFLOW_RUNS_DIR,
    DEFAULT_DOCUMENTS_DIR,
    DEFAULT_TEMPLATES_DIR,
    DEFAULT_OUTPUTS_DIR,
    DEFAULT_EXECUTIONS_DIR,
    DEFAULT_LOGS_DIR,
)


class Settings(BaseSettings):
    """
    Main application settings loaded from environment variables or .env files.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default=DEFAULT_APP_NAME)
    app_env: str = Field(default=DEFAULT_APP_ENV)
    app_debug: bool = Field(default=True)
    app_host: str = Field(default=DEFAULT_HOST)
    app_port: int = Field(default=DEFAULT_PORT)

    api_prefix: str = Field(default=API_PREFIX)
    log_level: str = Field(default=DEFAULT_LOG_LEVEL)

    cors_origins: list[str] = Field(default_factory=lambda: DEFAULT_CORS_ORIGINS.copy())

    local_storage_root: str = Field(default=DEFAULT_STORAGE_ROOT)
    workflow_runs_dir_name: str = Field(default=DEFAULT_WORKFLOW_RUNS_DIR)
    documents_dir_name: str = Field(default=DEFAULT_DOCUMENTS_DIR)
    templates_dir_name: str = Field(default=DEFAULT_TEMPLATES_DIR)
    outputs_dir_name: str = Field(default=DEFAULT_OUTPUTS_DIR)
    executions_dir_name: str = Field(default=DEFAULT_EXECUTIONS_DIR)
    logs_dir_name: str = Field(default=DEFAULT_LOGS_DIR)

    # Azure OpenAI
    azure_openai_endpoint: str | None = Field(default=None)
    azure_openai_api_key: str | None = Field(default=None)
    azure_openai_api_version: str = Field(default="2024-10-21")
    azure_openai_chat_deployment: str | None = Field(default=None)
    azure_openai_reasoning_deployment: str | None = Field(default=None)
    azure_openai_embedding_deployment: str | None = Field(default=None)
    azure_openai_stage3_chat_deployment: str = Field(default="gpt-5-mini")

    # Azure Document Intelligence
    azure_document_intelligence_endpoint: str | None = Field(default=None)
    azure_document_intelligence_key: str | None = Field(default=None)

    # Azure AI Search
    azure_search_endpoint: str | None = Field(default=None)
    azure_search_api_key: str | None = Field(default=None)
    azure_search_index_name: str = Field(default="sdlc_knowledge_index")
    azure_search_vector_field: str = Field(default="embedding")

    # Azure Blob Storage
    azure_storage_connection_string: str | None = Field(default=None)
    azure_storage_account_url: str | None = Field(default=None)
    azure_storage_container_name: str | None = Field(default=None)
    azure_storage_root_prefix: str = Field(default="sahil_storage")

    @property
    def storage_root_path(self) -> Path:
        return Path(self.local_storage_root)

    @property
    def workflow_runs_path(self) -> Path:
        return self.storage_root_path / self.workflow_runs_dir_name

    @property
    def documents_path(self) -> Path:
        return self.storage_root_path / self.documents_dir_name

    @property
    def templates_path(self) -> Path:
        return self.storage_root_path / self.templates_dir_name

    @property
    def outputs_path(self) -> Path:
        return self.storage_root_path / self.outputs_dir_name

    @property
    def executions_path(self) -> Path:
        return self.storage_root_path / self.executions_dir_name

    @property
    def logs_path(self) -> Path:
        return self.storage_root_path / self.logs_dir_name

    @property
    def azure_storage_root_prefix_normalized(self) -> str:
        return self.azure_storage_root_prefix.strip().strip("/") or "sahil_storage"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Cached settings loader so the app uses one shared settings instance.
    """
    return Settings()