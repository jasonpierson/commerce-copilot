from __future__ import annotations

# Deprecated compatibility wrapper.
# The canonical evaluator lives in app.retrieval.evals.evaluator.

from app.retrieval.evals.evaluator import (  # noqa: F401
    CaseScore,
    EvalCase,
    EvalRunnerError,
    RetrievalResult,
    coerce_result,
    doc_key_to_title,
    load_eval_set,
    normalize_section_title,
    retrieve_stub,
    retrieve_with_adapter,
    run_case,
    run_evaluation,
    summarize,
    write_report,
)
