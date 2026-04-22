from __future__ import annotations

import hashlib
from typing import Sequence


class DummyEmbedder:
    """
    Deterministic offline embedder for smoke tests only.
    Live ingestion and retrieval runtime paths use OpenAI embeddings.
    """

    def __init__(self, dimensions: int = 1536) -> None:
        self.dimensions = dimensions

    def embed_query(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        values = []
        for i in range(self.dimensions):
            byte = digest[i % len(digest)]
            values.append((byte / 255.0) * 2.0 - 1.0)
        return values

    def embed_many(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]
