from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import mean
from typing import Optional


@dataclass(slots=True)
class SourceDocument:
    file_path: str
    title: str
    doc_type: str
    doc_key: str
    audience: Optional[str]
    status: str
    source_name: str
    source_path: Optional[str]
    version: int
    raw_text: str


@dataclass(slots=True)
class Section:
    section_index: int
    title: Optional[str]
    body_text: str


@dataclass(slots=True)
class Chunk:
    chunk_index: int
    document_title: str
    doc_key: str
    doc_type: str
    audience: Optional[str]
    section_title: Optional[str]
    chunk_text: str
    token_count: int
    embedding: Optional[list[float]] = None


@dataclass(slots=True)
class IngestionSuccess:
    file_path: str
    doc_key: str
    chunk_count: int
    avg_chunk_tokens: float
    max_chunk_tokens: int


@dataclass(slots=True)
class IngestionFailure:
    file_path: str
    error: str


@dataclass(slots=True)
class IngestionReport:
    started_at: str
    finished_at: Optional[str] = None
    successes: list[IngestionSuccess] = field(default_factory=list)
    failures: list[IngestionFailure] = field(default_factory=list)

    @staticmethod
    def utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def start(cls) -> "IngestionReport":
        return cls(started_at=cls.utc_now_iso())

    def add_success(self, *, file_path: str, doc_key: str, chunks: list[Chunk]) -> None:
        token_counts = [chunk.token_count for chunk in chunks]
        self.successes.append(
            IngestionSuccess(
                file_path=file_path,
                doc_key=doc_key,
                chunk_count=len(chunks),
                avg_chunk_tokens=mean(token_counts) if token_counts else 0.0,
                max_chunk_tokens=max(token_counts) if token_counts else 0,
            )
        )

    def add_failure(self, *, file_path: str, error: str) -> None:
        self.failures.append(IngestionFailure(file_path=file_path, error=error))
