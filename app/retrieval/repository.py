from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import RetrievalRow

def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.12f}" for v in values) + "]"


@dataclass(slots=True)
class PostgresRetrievalRepository:
    dsn: str

    def search_vector_index(
        self,
        *,
        query_embedding: list[float],
        filters: dict,
        candidate_limit: int,
    ) -> list[RetrievalRow]:
        # Lazy import to avoid hard dependency in smoke tests
        try:
            import psycopg  # type: ignore
            from psycopg.rows import dict_row  # type: ignore
        except Exception as exc:  # pragma: no cover
            raise RuntimeError(
                "psycopg is required for PostgresRetrievalRepository; install 'psycopg[binary]'"
            ) from exc
        vector_value = _vector_literal(query_embedding)

        sql = """
        select
            dc.document_id,
            d.doc_key,
            d.title,
            d.doc_type,
            d.audience,
            dc.section_title,
            dc.chunk_index,
            dc.chunk_text,
            1 - (dc.embedding <=> %s::vector) as similarity_score
        from public.document_chunks dc
        join public.documents d
          on d.id = dc.document_id
        where d.status = %s
          and d.doc_type = any(%s)
          and (d.audience = any(%s) or d.audience is null)
        order by dc.embedding <=> %s::vector
        limit %s
        """

        params = [
            vector_value,
            filters["status"],
            filters["doc_types"],
            filters["audiences"],
            vector_value,
            candidate_limit,
        ]

        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

        return [
            RetrievalRow(
                document_id=row["document_id"],
                doc_key=row["doc_key"],
                title=row["title"],
                doc_type=row["doc_type"],
                audience=row["audience"],
                section_title=row["section_title"],
                chunk_index=row["chunk_index"],
                chunk_text=row["chunk_text"],
                similarity_score=float(row["similarity_score"]),
            )
            for row in rows
        ]

class RetrievalRepository(Protocol):
    def search_vector_index(
        self,
        *,
        query_embedding: list[float],
        filters: dict,
        candidate_limit: int,
    ) -> list[RetrievalRow]:
        ...


@dataclass(slots=True)
class FakeRetrievalRepository:
    """
    In-memory repository for smoke testing.
    Replace with a real Supabase/Postgres-backed repository.
    """

    rows: list[RetrievalRow]

    def search_vector_index(
        self,
        *,
        query_embedding: list[float],
        filters: dict,
        candidate_limit: int,
    ) -> list[RetrievalRow]:
        allowed_doc_types = set(filters["doc_types"])
        allowed_audiences = set(filters["audiences"])

        filtered = [
            row
            for row in self.rows
            if row.doc_type in allowed_doc_types
            and (row.audience in allowed_audiences or row.audience is None)
        ]
        filtered.sort(key=lambda r: r.similarity_score, reverse=True)
        return filtered[:candidate_limit]
