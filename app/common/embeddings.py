from __future__ import annotations

from openai import OpenAI

from app.common.config import EmbeddingConfig


class OpenAIEmbedder:
    def __init__(
        self,
        *,
        model: str,
        dimensions: int,
        api_key: str,
    ) -> None:
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is required for OpenAI embeddings")

        self.model = str(model)
        self.dimensions = int(dimensions)
        self.client = OpenAI(api_key=api_key)

    @classmethod
    def from_config(cls, config: EmbeddingConfig) -> "OpenAIEmbedder":
        return cls(
            model=config.model,
            dimensions=config.dimensions,
            api_key=config.openai_api_key,
        )

    def embed_query(self, text: str) -> list[float]:
        if not text or not text.strip():
            raise ValueError("Query text must not be empty")

        response = self.client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimensions,
            encoding_format="float",
        )
        return response.data[0].embedding

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = self.client.embeddings.create(
            model=self.model,
            input=texts,
            dimensions=self.dimensions,
            encoding_format="float",
        )
        return [item.embedding for item in response.data]
