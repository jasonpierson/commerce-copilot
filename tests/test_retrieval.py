from __future__ import annotations

from unittest import TestCase

from app.retrieval.dedupe import dedupe_results
from app.retrieval.evals.evaluator import normalize_section_title
from app.retrieval.models import RetrievalRow


def _row(*, doc_key: str, section_title: str | None, chunk_index: int, final_score: float) -> RetrievalRow:
    return RetrievalRow(
        document_id=f"doc-{doc_key}",
        doc_key=doc_key,
        title=doc_key,
        doc_type="policy",
        audience="support",
        section_title=section_title,
        chunk_index=chunk_index,
        chunk_text=f"chunk {chunk_index}",
        similarity_score=final_score,
        final_score=final_score,
    )


class RetrievalDedupeTests(TestCase):
    def test_dedupe_results_keeps_one_chunk_per_normalized_section(self) -> None:
        rows = [
            _row(doc_key="policy_returns_001", section_title="Eligibility", chunk_index=0, final_score=0.98),
            _row(doc_key="policy_returns_001", section_title="  eligibility  ", chunk_index=1, final_score=0.97),
            _row(doc_key="policy_returns_001", section_title="Exceptions", chunk_index=2, final_score=0.96),
        ]

        deduped = dedupe_results(rows, max_chunks_per_doc=3)

        self.assertEqual([row.chunk_index for row in deduped], [0, 2])

    def test_dedupe_results_respects_max_chunks_per_doc_without_hard_top_three_diversity(self) -> None:
        rows = [
            _row(doc_key="policy_returns_001", section_title="Eligibility", chunk_index=0, final_score=0.99),
            _row(doc_key="policy_returns_001", section_title="Exceptions", chunk_index=1, final_score=0.98),
            _row(doc_key="policy_returns_001", section_title="Escalations", chunk_index=2, final_score=0.97),
            _row(doc_key="sop_damaged_product_handling_001", section_title="Photos", chunk_index=0, final_score=0.96),
        ]

        deduped = dedupe_results(rows, max_chunks_per_doc=2)

        self.assertEqual([row.doc_key for row in deduped[:2]], ["policy_returns_001", "policy_returns_001"])
        self.assertEqual(len([row for row in deduped if row.doc_key == "policy_returns_001"]), 2)


class RetrievalEvaluatorNormalizationTests(TestCase):
    def test_normalize_section_title_collapses_formatting_noise(self) -> None:
        self.assertEqual(normalize_section_title("  **Customer Impact**  "), "customer impact")
