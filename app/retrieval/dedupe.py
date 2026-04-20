from __future__ import annotations

from collections import defaultdict
import re

from .config import RetrievalConfig
from .models import RetrievalRow


def dedupe_results(
    rows: list[RetrievalRow],
    max_chunks_per_doc: int = RetrievalConfig().max_chunks_per_doc,
) -> list[RetrievalRow]:
    def _normalize_section(title: str | None) -> str:
        if not title:
            return ""
        t = title.lower().strip()
        t = t.replace("**", "")
        t = re.sub(r"\s+", " ", t)
        return t

    output: list[RetrievalRow] = []
    per_doc_counts = defaultdict(int)
    seen_section_for_doc: set[tuple[str, str]] = set()

    # Rows are expected to be pre-sorted by descending final_score; keep first per section.
    for row in rows:
        if per_doc_counts[row.doc_key] >= max_chunks_per_doc:
            continue

        section_key = (row.doc_key, _normalize_section(row.section_title))

        # Enforce at most one chunk per section per document (section-aware dedupe)
        if section_key in seen_section_for_doc:
            continue

        seen_section_for_doc.add(section_key)
        per_doc_counts[row.doc_key] += 1
        output.append(row)

    return output


def enforce_top_n_doc_diversity(rows: list[RetrievalRow], n: int = 3) -> list[RetrievalRow]:
    if n <= 0 or not rows:
        return rows

    top_unique: list[RetrievalRow] = []
    seen: set[str] = set()
    rest: list[RetrievalRow] = []

    for row in rows:
        if len(top_unique) < n and row.doc_key not in seen:
            top_unique.append(row)
            seen.add(row.doc_key)
        else:
            rest.append(row)

    return top_unique + rest