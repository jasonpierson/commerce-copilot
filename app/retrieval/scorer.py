from __future__ import annotations

import os
import re

from .models import RetrievalRow


def _normalize(text: str | None) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = text.replace("**", "")
    text = re.sub(r"\s+", " ", text)
    return text


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9_]+", text.lower()))


def _keyword_overlap_score(query: str, text: str) -> float:
    q_tokens = _tokenize(query)
    t_tokens = _tokenize(text)

    if not q_tokens or not t_tokens:
        return 0.0

    overlap = q_tokens.intersection(t_tokens)
    if not overlap:
        return 0.0

    ratio = len(overlap) / max(len(q_tokens), 1)

    if ratio >= 0.6:
        return 0.12
    if ratio >= 0.4:
        return 0.08
    if ratio >= 0.2:
        return 0.04
    return 0.02


# Tunable weights via environment variables for fast A/B without code edits
SECTION_IN_QUERY_BOOST = float(os.getenv("SECTION_IN_QUERY_BOOST", "0.16"))
QUERY_IN_SECTION_BOOST = float(os.getenv("QUERY_IN_SECTION_BOOST", "0.10"))
SECTION_OVERLAP_MULT = float(os.getenv("SECTION_OVERLAP_MULT", "2.0"))
SECTION_HEADER_BOOST = float(os.getenv("SECTION_HEADER_BOOST", "0.06"))


def apply_post_retrieval_scoring(query: str, rows: list[RetrievalRow]) -> list[RetrievalRow]:
    query_norm = _normalize(query)

    for row in rows:
        score = float(row.similarity_score)

        title = _normalize(row.title)
        section = _normalize(row.section_title)
        text = _normalize(row.chunk_text)

        if title and title in query_norm:
            score += 0.12
        if section and section in query_norm:
            score += SECTION_IN_QUERY_BOOST

        if query_norm and title and query_norm in title:
            score += 0.06
        if query_norm and section and query_norm in section:
            score += QUERY_IN_SECTION_BOOST

        score += _keyword_overlap_score(query_norm, title) * 1.5
        score += _keyword_overlap_score(query_norm, section) * SECTION_OVERLAP_MULT
        score += _keyword_overlap_score(query_norm, text)

        # If the chunk explicitly carries a section header that matches, add a small boost
        if section and text and f"section: {section}" in text:
            score += SECTION_HEADER_BOOST

        row.final_score = score

    return sorted(rows, key=lambda r: r.final_score, reverse=True)