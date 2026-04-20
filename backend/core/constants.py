"""
Shared backend constants.
"""

API_PREFIX: str = "/api"

DEFAULT_APP_NAME: str = "backend"
DEFAULT_APP_ENV: str = "local"
DEFAULT_LOG_LEVEL: str = "INFO"

DEFAULT_HOST: str = "127.0.0.1"
DEFAULT_PORT: int = 8000

DEFAULT_CORS_ORIGINS: list[str] = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]

DEFAULT_STORAGE_ROOT: str = "backend/storage"
DEFAULT_WORKFLOW_RUNS_DIR: str = "workflow_runs"
DEFAULT_DOCUMENTS_DIR: str = "documents"
DEFAULT_TEMPLATES_DIR: str = "templates"
DEFAULT_OUTPUTS_DIR: str = "outputs"
DEFAULT_EXECUTIONS_DIR: str = "executions"
DEFAULT_LOGS_DIR: str = "logs"

HEALTH_PATH: str = "/health"
READY_PATH: str = "/ready"