from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from .models import Chunk, SourceDocument

logger = logging.getLogger(__name__)

try:
    import psycopg
except ImportError:  # pragma: no cover
    psycopg = None


@dataclass(slots=True)
class Repository:
    db_url: str | None
    dry_run: bool = False

    def _connect(self):
        if self.dry_run:
            return None
        if not self.db_url:
            raise RuntimeError("SUPABASE_DB_URL is required when dry_run is false")
        if psycopg is None:
            raise RuntimeError("psycopg is required for database writes")
        return psycopg.connect(self.db_url)

    def upsert_document_record(self, doc: SourceDocument) -> Optional[str]:
        if self.dry_run:
            logger.info("Dry run: would upsert document %s", doc.doc_key)
            return None

        query_select = "select id from public.documents where doc_key = %s"
        query_update = """
            update public.documents
            set title = %s,
                doc_type = %s,
                source_name = %s,
                source_path = %s,
                status = %s,
                audience = %s,
                updated_at = now()
            where id = %s
        """
        query_insert = """
            insert into public.documents (
                doc_key, title, doc_type, source_name, source_path, status, audience
            )
            values (%s, %s, %s, %s, %s, %s, %s)
            returning id
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query_select, (doc.doc_key,))
                row = cur.fetchone()
                if row:
                    document_id = str(row[0])
                    cur.execute(
                        query_update,
                        (
                            doc.title,
                            doc.doc_type,
                            doc.source_name,
                            doc.source_path,
                            doc.status,
                            doc.audience,
                            document_id,
                        ),
                    )
                    conn.commit()
                    return document_id

                cur.execute(
                    query_insert,
                    (
                        doc.doc_key,
                        doc.title,
                        doc.doc_type,
                        doc.source_name,
                        doc.source_path,
                        doc.status,
                        doc.audience,
                    ),
                )
                document_id = str(cur.fetchone()[0])
                conn.commit()
                return document_id

    def delete_existing_chunks_for_document(self, document_id: str | None) -> None:
        if self.dry_run or document_id is None:
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("delete from public.document_chunks where document_id = %s", (document_id,))
                conn.commit()

    def insert_chunk_records(self, document_id: str | None, chunks: list[Chunk], embedding_model: str) -> None:
        if self.dry_run or document_id is None:
            logger.info("Dry run: would insert %s chunks", len(chunks))
            return

        query = """
            insert into public.document_chunks (
                document_id,
                chunk_index,
                chunk_text,
                embedding,
                token_count,
                section_title
            )
            values (%s, %s, %s, %s::vector, %s, %s)
        """

        with self._connect() as conn:
            with conn.cursor() as cur:
                for chunk in chunks:
                    embedding_literal = "[" + ",".join(f"{value:.8f}" for value in (chunk.embedding or [])) + "]"
                    cur.execute(
                        query,
                        (
                            document_id,
                            chunk.chunk_index,
                            chunk.chunk_text,
                            embedding_literal,
                            chunk.token_count,
                            chunk.section_title,
                        ),
                    )
                conn.commit()
