# Retrieval Updates and Dedupe Changes (Orchestrator Summary)

## Objective
- Improve section precision and reduce duplicate crowding in top results without regressing boundary correctness.

## Key Changes
- Section-aware dedupe
  - [app/retrieval/dedupe.py](../app/retrieval/dedupe.py):
    - Keep at most one chunk per section per document (normalized by lowercase/trim/remove `**`, collapse whitespace).
    - New `enforce_top_n_doc_diversity()` to ensure at most one result per document within the top-3.
- Per-route and env-based caps
  - [app/retrieval/config.py](../app/retrieval/config.py):
    - `max_chunks_per_doc` now read from `MAX_CHUNKS_PER_DOC` (default 2).
    - Route-specific caps with env fallbacks:
      - `POLICY_QA_MAX_CHUNKS_PER_DOC`
      - `INCIDENT_SUMMARY_MAX_CHUNKS_PER_DOC`
      - `ESCALATION_GUIDANCE_MAX_CHUNKS_PER_DOC`
  - [app/retrieval/service.py](../app/retrieval/service.py): apply per-route cap and enforce top-3 diversity before final `top_k` slice.
- Scoring adjustments (section-first)
  - [app/retrieval/scorer.py](../app/retrieval/scorer.py):
    - Boosted section-title influence and made weights env-tunable:
      - `SECTION_IN_QUERY_BOOST` (default 0.16)
      - `QUERY_IN_SECTION_BOOST` (default 0.10)
      - `SECTION_OVERLAP_MULT` (default 2.0)
      - `SECTION_HEADER_BOOST` (default 0.06) when chunk text contains matching "Section: <title>".
- Developer ergonomics / reliability
  - [scripts/run_retrieval_smoke_test.py](../scripts/run_retrieval_smoke_test.py): add project root to `sys.path` and use `dataclasses.asdict`.
  - [app/retrieval/repository.py](../app/retrieval/repository.py): lazy-import `psycopg` inside `PostgresRetrievalRepository` (smoke test works without DB lib).
  - [pyproject.toml](../pyproject.toml): limit setuptools discovery to `app*` (fix editable install error about multiple top-level packages).

## Env Knobs
- Retrieval caps
  - `MAX_CHUNKS_PER_DOC` (global, default 2)
  - `POLICY_QA_MAX_CHUNKS_PER_DOC` (fallback to global)
  - `INCIDENT_SUMMARY_MAX_CHUNKS_PER_DOC` (fallback to global)
  - `ESCALATION_GUIDANCE_MAX_CHUNKS_PER_DOC` (fallback to global)
- Scorer weights
  - `SECTION_IN_QUERY_BOOST` (default 0.16)
  - `QUERY_IN_SECTION_BOOST` (default 0.10)
  - `SECTION_OVERLAP_MULT` (default 2.0)
  - `SECTION_HEADER_BOOST` (default 0.06)
- Embeddings and backend
  - `OPENAI_API_KEY`, `EMBEDDING_MODEL` (default `text-embedding-3-small`), `EMBEDDING_DIMENSIONS` (default `1536`)
  - `SUPABASE_DB_URL` for Postgres

## How to Run
- Smoke test (no DB/API required):
```bash
python3 scripts/run_retrieval_smoke_test.py
```
- Full retrieval eval (adapter mode, real embeddings + DB):
```bash
# Required env (example)
export SUPABASE_DB_URL='postgresql://<user>:<pass>@<host>:5432/postgres'
export OPENAI_API_KEY='<your-openai-key>'

# Optional knobs
export POLICY_QA_MAX_CHUNKS_PER_DOC=1
export SECTION_IN_QUERY_BOOST=0.24
export QUERY_IN_SECTION_BOOST=0.16
export SECTION_OVERLAP_MULT=3.0
export SECTION_HEADER_BOOST=0.12

python3 scripts/run_retrieval_eval.py --mode adapter
```
- Report: [retrieval_eval_report.json](../retrieval_eval_report.json)

## Current Eval Snapshot (latest report)
- From [retrieval_eval_report.json](../retrieval_eval_report.json) summary:
  - `top_1_hit_rate`: 0.8667
  - `top_3_hit_rate`: 1.0
  - `section_match_top_3_rate`: 0.5333
  - `retrieval_boundary_correct_rate`: 1.0
  - `unexpected_noise_top_3_rate`: 0.4667

Notes:
- Top-3 diversity rule is active (1-per-doc in top-3), which reduces duplicate crowding but may trade off with noise when replacements are not expected docs.
- Use per-route cap (e.g., `POLICY_QA_MAX_CHUNKS_PER_DOC=1`) to increase cross-doc diversity where desired.
- Section-first scorer knobs are now tunable without code edits for fast A/B.

## Suggested Next Steps
- Lock in a per-route cap profile (e.g., policy=1, incident=2).
- Iterate section weights with small deltas to lift `section_match_top_3_rate` while monitoring `top_1_hit_rate`.
- Optionally penalize multiple results from the same doc within top-3 beyond the diversity rule (tiny penalty) if noise persists.
