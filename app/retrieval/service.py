from __future__ import annotations

from .audit import AuditSink
from .dedupe import dedupe_results
from .exceptions import RetrievalError
from .filters import build_metadata_filters
from .models import RetrievalQueryRequest, RetrievalResult
from .policy import build_retrieval_policy
from .query_normalizer import normalize_query
from .scorer import apply_post_retrieval_scoring


class RetrievalService:
    def __init__(self, repository, config, embedder, audit_sink: AuditSink):
        self.repository = repository
        self.config = config
        self.embedder = embedder
        self.audit_sink = audit_sink

    def retrieve_context(
        self,
        req: RetrievalQueryRequest,
        *,
        request_id: str,
        user_id: str,
    ) -> list[RetrievalResult]:
        try:
            policy = build_retrieval_policy(req, self.config)
            normalized_query = normalize_query(req.query)

            filters = build_metadata_filters(
                allowed_doc_types=policy.allowed_doc_types,
                audience_filter=policy.allowed_audiences,
            )

            query_embedding = self.embedder.embed_query(normalized_query)

            candidate_rows = self.repository.search_vector_index(
                query_embedding=query_embedding,
                filters=filters,
                candidate_limit=policy.candidate_limit,
            )

            scored_rows = apply_post_retrieval_scoring(normalized_query, candidate_rows)

            # Route-specific per-doc caps for diversity/precision balance
            if req.route_type == "policy_qa":
                per_doc_cap = self.config.policy_qa_max_chunks_per_doc
            elif req.route_type == "incident_summary":
                per_doc_cap = self.config.incident_summary_max_chunks_per_doc
            elif req.route_type == "escalation_guidance":
                per_doc_cap = self.config.escalation_guidance_max_chunks_per_doc
            else:
                per_doc_cap = self.config.max_chunks_per_doc

            deduped_rows = dedupe_results(scored_rows, max_chunks_per_doc=per_doc_cap)
            final_rows = deduped_rows[: policy.top_k]

            self.audit_sink.log_event(
                event_type="retrieval_executed",
                request_id=request_id,
                route_type=req.route_type,
                user_id=user_id,
                query=req.query,
                doc_keys=[row.doc_key for row in final_rows],
                result_count=len(final_rows),
            )

            return [
                RetrievalResult(
                    document_id=row.document_id,
                    doc_key=row.doc_key,
                    title=row.title,
                    doc_type=row.doc_type,
                    audience=row.audience,
                    section_title=row.section_title,
                    chunk_index=row.chunk_index,
                    chunk_text=row.chunk_text,
                    relevance_score=row.final_score,
                )
                for row in final_rows
            ]

        except Exception as exc:
            raise RetrievalError("RETRIEVAL_FAILED") from exc
