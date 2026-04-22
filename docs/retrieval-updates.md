# Retrieval Updates

## Current Baseline

- Date: `2026-04-22`
- Embedding model: `text-embedding-3-small`
- Embedding dimensions: `1536`
- Canonical evaluator: `app/retrieval/evals/evaluator.py`
- Eval command:

```bash
source .venv/bin/activate
set -a
source .env.local
set +a
python3 scripts/run_retrieval_eval.py --mode adapter
```

## Baseline Retrieval Settings

- Per-route chunk caps:
  - policy: `2`
  - incident: `2`
  - escalation: `2`
- Section-aware dedupe: enabled
- Hard top-3 document diversity enforcement: disabled
- Max chunks per doc:
  - `MAX_CHUNKS_PER_DOC=2`
  - `POLICY_QA_MAX_CHUNKS_PER_DOC=2`
  - `INCIDENT_SUMMARY_MAX_CHUNKS_PER_DOC=2`
  - `ESCALATION_GUIDANCE_MAX_CHUNKS_PER_DOC=2`

## Baseline Metrics

From `artifacts/retrieval_eval_report.json` after real ingestion and live adapter evaluation:

- `top_1_hit_rate`: `1.0`
- `top_3_hit_rate`: `1.0`
- `section_match_top_3_rate`: `0.8667`
- `retrieval_boundary_correct_rate`: `1.0`
- `unexpected_noise_top_3_rate`: `0.0`

## What Changed To Reach This Baseline

- Removed the hard top-3 cross-document diversity behavior from the live retrieval path
- Kept section-aware dedupe
- Kept per-route per-document caps at `2/2/2`
- Re-ingested the corpus with real OpenAI embeddings
- Verified retrieval runtime and ingestion share the same embedding defaults

## Known Weaknesses

- Policy queries still often return multiple strong chunks from the same expected document family, which is good for precision but can reduce result spread
- The eval set is intentionally compact; broader corpus growth may expose new edge cases
- Approval/inventory/incident structured flows are separate from retrieval quality and should be validated independently

## Section Precision Status

- Current `section_match_top_3_rate`: `0.8667`
- Target from the tuning plan: `>= 0.65`
- Current `top_1_hit_rate`: `1.0`
- Current `unexpected_noise_top_3_rate`: `0.0`

Because the live baseline already exceeds the section-precision target without introducing noise, no additional scorer-weight tuning was applied after this baseline was established.

## How To Rebuild This Baseline

1. Re-ingest the corpus:

```bash
source .venv/bin/activate
set -a
source .env.local
set +a
python -m app.ingestion.runner --corpus-root ./corpus
```

2. Re-run retrieval evaluation:

```bash
source .venv/bin/activate
set -a
source .env.local
set +a
python3 scripts/run_retrieval_eval.py --mode adapter
```

3. Confirm the current baseline targets:

- `top_1_hit_rate >= 0.90`
- `top_3_hit_rate == 1.0`
- `retrieval_boundary_correct_rate == 1.0`
- `unexpected_noise_top_3_rate <= 0.15`

## Artifact

- Report: `artifacts/retrieval_eval_report.json`
