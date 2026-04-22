from __future__ import annotations

from dataclasses import dataclass, field
import os


DB_APP_SCHEMA = os.getenv("DB_APP_SCHEMA", "app_private")


def _env_str(name: str, default: str) -> str:
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


@dataclass(slots=True)
class EmbeddingConfig:
    provider: str = field(default_factory=lambda: _env_str("EMBEDDING_PROVIDER", "openai"))
    model: str = field(default_factory=lambda: _env_str("EMBEDDING_MODEL", "text-embedding-3-small"))
    dimensions: int = field(default_factory=lambda: _env_int("EMBEDDING_DIMENSIONS", 1536))
    openai_api_key: str = field(default_factory=lambda: _env_str("OPENAI_API_KEY", ""))
