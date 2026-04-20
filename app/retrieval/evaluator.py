from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


@dataclass
class EvalCase:
    id: str
    route_type: str
    user_role: str
    query: str
    expected_doc_keys: List[str]
    expected_section_titles: List[str]
    should_use_retrieval: bool
    notes: str


@dataclass
class RetrievalResult:
    doc_key: str
    title: str
    section_title: Optional[str]
    chunk_text: str
    relevance_score: float


@dataclass
class CaseScore:
    id: str
    route_type: str
    query: str
    should_use_retrieval: bool
    result_count: int
    top_result_doc_key: Optional[str]
    top_3_doc_keys: List[str]
    top_1_hit: bool
    top_3_hit: bool
    section_match_top_3: bool
    unexpected_noise_top_3: bool
    used_retrieval_correctly: bool
    notes: str


class EvalRunnerError(Exception):
    pass


def load_eval_set(path: Path) -> List[EvalCase]:
    cases: List[EvalCase] = []
    with path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvalRunnerError(f"Invalid JSON on line {line_no}: {exc}") from exc
            cases.append(EvalCase(**raw))
    return cases


def doc_key_to_title(doc_key: str) -> str:
    mapping = {
        "policy_returns_001": "Returns Policy",
        "sop_damaged_product_handling_001": "Damaged Product Handling SOP",
        "policy_product_availability_001": "Product Availability Policy",
        "sop_inventory_availability_001": "Inventory Availability SOP",
        "runbook_checkout_incident_001": "Checkout Incident Runbook",
        "runbook_customer_impact_assessment_001": "Customer Impact Assessment Runbook",
        "incident_playbook_mobile_checkout_001": "Mobile Checkout Incident Playbook",
        "escalation_procedure_incident_escalation_001": "Incident Escalation Procedure",
        "matrix_priority_escalation_001": "Priority Escalation Matrix",
    }
    return mapping.get(doc_key, doc_key)


def coerce_result(raw: Any) -> RetrievalResult:
    if isinstance(raw, RetrievalResult):
        return raw
    if isinstance(raw, dict):
        return RetrievalResult(
            doc_key=raw["doc_key"],
            title=raw.get("title", raw["doc_key"]),
            section_title=raw.get("section_title"),
            chunk_text=raw.get("chunk_text", ""),
            relevance_score=float(raw.get("relevance_score", 0.0)),
        )
    raise EvalRunnerError(f"Cannot coerce retrieval result: {raw!r}")


def retrieve_stub(case: EvalCase, top_k: int = 5) -> List[RetrievalResult]:
    if not case.should_use_retrieval:
        return []

    results: List[RetrievalResult] = []
    for idx, doc_key in enumerate(case.expected_doc_keys[:top_k]):
        section = case.expected_section_titles[idx] if idx < len(case.expected_section_titles) else None
        results.append(
            RetrievalResult(
                doc_key=doc_key,
                title=doc_key_to_title(doc_key),
                section_title=section,
                chunk_text=f"Stub chunk for {doc_key}",
                relevance_score=max(0.99 - (idx * 0.05), 0.5),
            )
        )

    filler_docs = [
        "policy_returns_001",
        "sop_inventory_availability_001",
        "runbook_checkout_incident_001",
        "matrix_priority_escalation_001",
    ]
    for filler in filler_docs:
        if len(results) >= top_k:
            break
        if filler in case.expected_doc_keys:
            continue
        results.append(
            RetrievalResult(
                doc_key=filler,
                title=doc_key_to_title(filler),
                section_title=None,
                chunk_text=f"Stub chunk for {filler}",
                relevance_score=0.2,
            )
        )
    return results


def retrieve_with_adapter(case: EvalCase, top_k: int = 5) -> List[RetrievalResult]:
    """Wire this to the real retrieval service.

    Replace the body of this function once the project retrieval service is ready.
    Expected return: list[RetrievalResult] or list[dict] with equivalent keys.
    """
    raise NotImplementedError(
        "Adapter mode is not wired yet. Replace retrieve_with_adapter() with a call into the real retrieval service."
    )


def run_case(case: EvalCase, mode: str, top_k: int) -> CaseScore:
    if mode == "stub":
        results = retrieve_stub(case, top_k=top_k)
    elif mode == "adapter":
        raw_results = retrieve_with_adapter(case, top_k=top_k)
        results = [coerce_result(r) for r in raw_results]
    else:
        raise EvalRunnerError(f"Unsupported mode: {mode}")

    top_3 = results[:3]
    top_3_doc_keys = [r.doc_key for r in top_3]
    top_result_doc_key = results[0].doc_key if results else None

    top_1_hit = bool(case.expected_doc_keys) and top_result_doc_key in case.expected_doc_keys
    top_3_hit = any(r.doc_key in case.expected_doc_keys for r in top_3) if case.expected_doc_keys else False
    section_match_top_3 = (
        any(r.section_title in case.expected_section_titles for r in top_3 if r.section_title)
        if case.expected_section_titles
        else False
    )

    unexpected_noise_top_3 = False
    if case.expected_doc_keys:
        allowed = set(case.expected_doc_keys)
        top_noise = [doc for doc in top_3_doc_keys if doc not in allowed]
        unexpected_noise_top_3 = len(top_noise) >= 2

    used_retrieval_correctly = case.should_use_retrieval or len(results) == 0

    return CaseScore(
        id=case.id,
        route_type=case.route_type,
        query=case.query,
        should_use_retrieval=case.should_use_retrieval,
        result_count=len(results),
        top_result_doc_key=top_result_doc_key,
        top_3_doc_keys=top_3_doc_keys,
        top_1_hit=top_1_hit,
        top_3_hit=top_3_hit,
        section_match_top_3=section_match_top_3,
        unexpected_noise_top_3=unexpected_noise_top_3,
        used_retrieval_correctly=used_retrieval_correctly,
        notes=case.notes,
    )


def summarize(scores: List[CaseScore]) -> Dict[str, Any]:
    retrieval_cases = [s for s in scores if s.should_use_retrieval]
    tool_only_cases = [s for s in scores if not s.should_use_retrieval]

    def rate(items: Iterable[CaseScore], attr: str) -> float:
        items = list(items)
        if not items:
            return 0.0
        hits = sum(1 for item in items if getattr(item, attr))
        return round(hits / len(items), 4)

    return {
        "total_cases": len(scores),
        "retrieval_cases": len(retrieval_cases),
        "tool_only_cases": len(tool_only_cases),
        "top_1_hit_rate": rate(retrieval_cases, "top_1_hit"),
        "top_3_hit_rate": rate(retrieval_cases, "top_3_hit"),
        "section_match_top_3_rate": rate(retrieval_cases, "section_match_top_3"),
        "retrieval_boundary_correct_rate": rate(scores, "used_retrieval_correctly"),
        "unexpected_noise_top_3_rate": rate(retrieval_cases, "unexpected_noise_top_3"),
    }


def run_evaluation(eval_path: Path, mode: str, top_k: int) -> Dict[str, Any]:
    cases = load_eval_set(eval_path)
    scores = [run_case(case, mode=mode, top_k=top_k) for case in cases]
    summary = summarize(scores)
    return {
        "summary": summary,
        "case_scores": [asdict(s) for s in scores],
    }


def write_report(report: Dict[str, Any], output_path: Path) -> None:
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
