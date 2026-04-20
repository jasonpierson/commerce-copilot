from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(slots=True)
class RetrievalQueryRequest:
    query: str
    route_type: str
    user_role: str
    top_k: int = 5
    allowed_doc_types: Optional[list[str]] = None
    audience_filter: Optional[str] = None
    incident_context: Optional[dict[str, Any]] = None


@dataclass(slots=True)
class RetrievalPolicy:
    allowed_doc_types: list[str]
    allowed_audiences: set[str]
    top_k: int
    candidate_limit: int


@dataclass(slots=True)
class RetrievalRow:
    document_id: str
    doc_key: str
    title: str
    doc_type: str
    audience: Optional[str]
    section_title: Optional[str]
    chunk_index: int
    chunk_text: str
    similarity_score: float
    final_score: float = 0.0


@dataclass(slots=True)
class RetrievalResult:
    document_id: str
    doc_key: str
    title: str
    doc_type: str
    audience: Optional[str]
    section_title: Optional[str]
    chunk_index: int
    chunk_text: str
    relevance_score: float


@dataclass(slots=True)
class RetrievalAuditPayload:
    request_id: str
    route_type: str
    user_id: str
    query: str
    doc_keys: list[str] = field(default_factory=list)
    result_count: int = 0
