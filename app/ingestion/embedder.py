from __future__ import annotations

from typing import Protocol

from app.common.config import EmbeddingConfig
from app.common.embeddings import OpenAIEmbedder

class Embedder(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...

def build_embedder(config: EmbeddingConfig):
    if config.provider != "openai":
        raise ValueError(
            "Ingestion requires EMBEDDING_PROVIDER=openai so stored chunk embeddings "
            "match the live retrieval runtime."
        )
    return OpenAIEmbedder.from_config(config)
