from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Protocol

from app.common.config import EmbeddingConfig
from app.common.embeddings import OpenAIEmbedder

class Embedder(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        ...


@dataclass(slots=True)
class DummyEmbedder:
    dimensions: int = 1536

    def _embed_one(self, text: str) -> list[float]:
        values: list[float] = []
        seed = text.encode("utf-8")
        counter = 0
        while len(values) < self.dimensions:
            digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
            for i in range(0, len(digest), 4):
                chunk = digest[i : i + 4]
                if len(chunk) < 4:
                    continue
                integer = int.from_bytes(chunk, "big", signed=False)
                normalized = (integer / 2**32) * 2 - 1
                values.append(normalized)
                if len(values) >= self.dimensions:
                    break
            counter += 1

        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]


class UnsupportedEmbedder:
    def __init__(self, provider: str) -> None:
        self.provider = provider

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError(
            f"Embedding provider '{self.provider}' is not implemented in this scaffold. "
            "Use EMBEDDING_PROVIDER=dummy for offline testing or add a real provider implementation."
        )



def build_embedder(config: EmbeddingConfig):
    if config.provider == "openai":
        return OpenAIEmbedder(
            model=config.model,
            dimensions=config.dimensions,
            api_key=config.openai_api_key,
        )

    if config.provider == "dummy":
        return DummyEmbedder(dimensions=config.dimensions)

    raise ValueError(f"Unsupported embedding provider: {config.provider}")