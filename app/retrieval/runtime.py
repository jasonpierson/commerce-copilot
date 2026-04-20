from __future__ import annotations

import os
from functools import lru_cache

from app.common.config import EmbeddingConfig
from app.common.embeddings import OpenAIEmbedder
from .audit import AuditSink
from .config import RetrievalConfig
from .embedder import DummyEmbedder
from .repository import PostgresRetrievalRepository
from .service import RetrievalService


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _build_query_embedder(config: EmbeddingConfig):
    if config.provider == "openai":
        return OpenAIEmbedder.from_config(config)
    if config.provider == "dummy":
        return DummyEmbedder(dimensions=config.dimensions)
    raise RuntimeError(f"Unsupported embedding provider: {config.provider}")


@lru_cache(maxsize=1)
def build_retrieval_service() -> RetrievalService:
    embedding_config = EmbeddingConfig()

    repository = PostgresRetrievalRepository(dsn=_require_env("SUPABASE_DB_URL"))
    embedder = _build_query_embedder(embedding_config)

    return RetrievalService(
        repository=repository,
        config=RetrievalConfig(),
        embedder=embedder,
        audit_sink=AuditSink(),
    )
