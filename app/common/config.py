from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version as package_version
import os


DB_APP_SCHEMA = os.getenv("DB_APP_SCHEMA", "app_private")
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
APP_NAME = "Governed Commerce Operations Copilot API"
PACKAGE_NAME = "commerce-ops-copilot"

REQUIRED_RUNTIME_ENV_VARS = (
    "SUPABASE_DB_URL",
    "OPENAI_API_KEY",
)

READINESS_ONLY_ENV_VARS = (
    "DEMO_ACCESS_PASSWORD",
)


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def missing_required_runtime_env(*, app_env: str | None = None) -> list[str]:
    effective_env = (app_env or APP_ENV).strip().lower()
    required = list(REQUIRED_RUNTIME_ENV_VARS)
    if effective_env == "production":
        required.extend(READINESS_ONLY_ENV_VARS)
    return [name for name in required if not os.getenv(name, "").strip()]


def validate_runtime_environment(*, app_env: str | None = None) -> None:
    missing = [name for name in REQUIRED_RUNTIME_ENV_VARS if not os.getenv(name, "").strip()]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"Missing required runtime environment variables: {joined}")


def _default_app_version() -> str:
    try:
        return package_version(PACKAGE_NAME)
    except PackageNotFoundError:
        return "0.1.0"


@dataclass(frozen=True, slots=True)
class BuildMetadata:
    app_name: str
    app_version: str
    git_sha: str
    build_timestamp: str
    app_env: str


def get_build_metadata() -> BuildMetadata:
    return BuildMetadata(
        app_name=os.getenv("APP_NAME", APP_NAME).strip() or APP_NAME,
        app_version=os.getenv("APP_VERSION", _default_app_version()).strip() or _default_app_version(),
        git_sha=os.getenv("GIT_SHA", "unknown").strip() or "unknown",
        build_timestamp=os.getenv("BUILD_TIMESTAMP", "unknown").strip() or "unknown",
        app_env=os.getenv("APP_ENV", APP_ENV).strip().lower() or APP_ENV,
    )


@dataclass(slots=True)
class EmbeddingConfig:
    provider: str = field(default_factory=lambda: _env_str("EMBEDDING_PROVIDER", "openai"))
    model: str = field(default_factory=lambda: _env_str("EMBEDDING_MODEL", "text-embedding-3-small"))
    dimensions: int = field(default_factory=lambda: _env_int("EMBEDDING_DIMENSIONS", 1536))
    openai_api_key: str = field(default_factory=lambda: _env_str("OPENAI_API_KEY", ""))
