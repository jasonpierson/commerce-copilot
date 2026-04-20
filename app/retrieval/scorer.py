from __future__ import annotations

import os
import re
from collections.abc import Iterable

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
SECTION_IN_QUERY_BOOST = float(os.getenv("SECTION_IN_QUERY_BOOST", "0.10"))
QUERY_IN_SECTION_BOOST = float(os.getenv("QUERY_IN_SECTION_BOOST", "0.06"))
SECTION_OVERLAP_MULT = float(os.getenv("SECTION_OVERLAP_MULT", "1.3"))
SECTION_HEADER_BOOST = float(os.getenv("SECTION_HEADER_BOOST", "0.00"))


def _contains_any(text: str, phrases: Iterable[str]) -> bool:
    return any(phrase in text for phrase in phrases)


def _route_alignment_score(query: str, row: RetrievalRow, route_type: str | None) -> float:
    if not route_type:
        return 0.0

    combined = " ".join(
        part
        for part in (_normalize(row.title), _normalize(row.section_title), _normalize(row.chunk_text))
        if part
    )
    score = 0.0

    availability_query = _contains_any(
        query,
        ("inventory", "availability", "low stock", "low-stock", "restock", "in stock", "stock"),
    )
    communication_query = _contains_any(
        query,
        ("customer", "customers", "talk", "describe", "promise", "say"),
    )
    damage_query = _contains_any(query, ("damaged", "damage", "photo", "photos"))
    return_query = _contains_any(query, ("return", "non-returnable", "refund"))
    escalation_query = _contains_any(query, ("escalate", "escalation"))
    triage_query = _contains_any(query, ("first", "initial", "check", "triage"))
    impact_query = _contains_any(query, ("impact", "harm"))
    mobile_query = "mobile" in query
    resolution_query = _contains_any(query, ("stable", "close", "resolved", "resolution", "handoff"))

    if route_type == "policy_qa":
        if availability_query:
            if _contains_any(
                combined,
                (
                    "inventory",
                    "availability",
                    "low confidence inventory",
                    "low availability",
                    "customer-facing commitments",
                    "availability status definitions",
                    "customer communication guidance",
                ),
            ):
                score += 0.08
            if communication_query and _contains_any(
                combined,
                ("customer communication", "customer-facing", "communication guidance", "commitments"),
            ):
                score += 0.04
            if not (damage_query or return_query) and _contains_any(
                combined, ("return", "damaged", "damage", "refund")
            ):
                score -= 0.05

        if damage_query and _contains_any(
            combined, ("damaged", "damage", "photo", "photos", "documentation", "verification")
        ):
            score += 0.08

        if return_query and _contains_any(
            combined, ("return", "non-returnable", "eligibility", "approved return")
        ):
            score += 0.07

        if escalation_query and _contains_any(combined, ("escalation", "threshold")):
            score += 0.05

    elif route_type == "incident_summary":
        if mobile_query and _contains_any(
            combined, ("mobile", "mobile web", "mobile checkout", "common symptoms", "known failure")
        ):
            score += 0.08

        if impact_query and _contains_any(
            combined,
            ("impact", "customer impact", "impact categories", "impact summary", "evidence sources"),
        ):
            score += 0.08

        if triage_query and _contains_any(
            combined,
            (
                "initial triage",
                "core verification checks",
                "immediate actions",
                "first-response",
                "when to use this runbook",
            ),
        ):
            score += 0.10

        if resolution_query and _contains_any(
            combined, ("resolution and handoff", "exit criteria", "stable")
        ):
            score += 0.08

        if triage_query and _contains_any(
            combined,
            ("communication guidance", "resolution and handoff", "exit criteria", "escalation rules"),
        ):
            score -= 0.05

    elif route_type == "escalation_guidance":
        if escalation_query and _contains_any(combined, ("escalation", "priority")):
            score += 0.07

        if _contains_any(query, ("approve", "approval", "allowed")) and _contains_any(
            combined, ("approve", "approval", "who may approve")
        ):
            score += 0.08

        if _contains_any(query, ("high priority", "sev1", "sev2")) and _contains_any(
            combined, ("high priority", "high priority criteria")
        ):
            score += 0.07

        if _contains_any(query, ("medium priority", "medium")) and _contains_any(
            combined, ("medium priority", "medium priority criteria")
        ):
            score += 0.07

    return score


def apply_post_retrieval_scoring(
    query: str,
    rows: list[RetrievalRow],
    *,
    route_type: str | None = None,
) -> list[RetrievalRow]:
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
        score += _route_alignment_score(query_norm, row, route_type)

        # If the chunk explicitly carries a section header that matches, add a small boost
        if section and text and f"section: {section}" in text:
            score += SECTION_HEADER_BOOST

        row.final_score = score

    return sorted(rows, key=lambda r: r.final_score, reverse=True)
