# AI Handoff

## Project

Governed Commerce Operations Copilot

Internal AI assistant for commerce operations, support, and engineering support teams.

Primary v1 capabilities:
- answer policy and process questions with citations
- retrieve structured operational data through tools
- summarize incidents or issues
- support one approval-gated escalation action
- record audit events

## Current architecture direction

System shape:
- RAG + tools + approval gate
- synthetic enterprise corpus instead of live connectors for v1
- Supabase/Postgres as the backend datastore
- FastAPI-style backend/orchestrator
- retrieval over document corpus
- structured tools for product, inventory, incident, approval data
- audit layer across request, routing, retrieval, tools, approvals, and responses

Primary user:
- commerce operations / support / engineering support

Top 3 jobs to be done:
- answer policy and process questions with citations
- retrieve structured operational data
- summarize incidents or issues

## Core data sources in v1

Unstructured corpus:
- markdown documents exported from Google Docs with YAML frontmatter

Structured data:
- Supabase / Postgres

Removed from v1:
- Slack
- live Notion connector
- live MongoDB access

## Repo shape

Important directories:

```text
app/
  common/
    config.py
    embeddings.py
  ingestion/
    config.py
    models.py
    loader.py
    normalizer.py
    segmenter.py
    chunker.py
    embedder.py
    repository.py
    report.py
    runner.py
  retrieval/
    audit.py
    config.py
    dedupe.py
    embedder.py
    exceptions.py
    filters.py
    models.py
    policy.py
    query_normalizer.py
    repository.py
    runtime.py
    scorer.py
    service.py
    evals/
      __init__.py
      evaluator.py
      retrieval_eval_set.jsonl
scripts/
  run_retrieval_eval.py
corpus/
  policy/
  sop/
  runbook/
  incident_playbook/
  escalation_procedure/
  matrix/
docs/
  ai-handoff.md
```

## Embedding setup

Shared embedding config now lives in:
- `app/common/config.py`

Real embedder implementation now lives in:
- `app/common/embeddings.py`

Important rule:
- ingestion and retrieval must use the same embedding provider, model, and dimensions

Current intended real model:
- `text-embedding-3-small`
- dimensions: `1536`

Environment variables expected:
- `OPENAI_API_KEY`
- `SUPABASE_DB_URL`
- `EMBEDDING_PROVIDER`
- `EMBEDDING_MODEL`
- `EMBEDDING_DIMENSIONS`
- `MAX_CHUNKS_PER_DOC`

## Corpus / ingestion status

Corpus was authored in Google Docs, then exported to markdown.

Markdown convention:
- YAML frontmatter at top
- H1 title matching `title`
- H2 section headings
- files organized under `corpus/<doc_type>/`

Current corpus includes:
- Returns Policy
- Product Availability Policy
- Damaged Product Handling SOP
- Inventory Availability SOP
- Fulfillment Exception Handling SOP
- Checkout Incident Runbook
- Customer Impact Assessment Runbook
- Mobile Checkout Incident Playbook
- Incident Escalation Procedure
- Priority Escalation Matrix

Ingestion approach:
- section-aware chunking
- target chunk size roughly 250–450 tokens
- overlap only when needed for long sections
- chunks stored in `document_chunks`
- metadata stored in `documents`

## Retrieval status

Retrieval eval has been built and runs through:
- `app/retrieval/evals/retrieval_eval_set.jsonl`
- `scripts/run_retrieval_eval.py --mode adapter`

Current eval baseline after the retrieval fixes:
- top_1_hit_rate: 0.9333
- top_3_hit_rate: 1.0
- section_match_top_3_rate: 0.5333
- retrieval_boundary_correct_rate: 1.0
- unexpected_noise_top_3_rate: 0.0667

Interpretation:
- document-family retrieval is strong
- boundary handling is correct
- section precision is the weakest remaining retrieval metric
- duplicate doc crowding still appears in some top results

## Retrieval changes already made

- dedupe uses configurable `MAX_CHUNKS_PER_DOC`
- route doc types were tightened:
  - policy_qa -> policy + sop
  - incident_summary -> runbook + incident_playbook
  - escalation_guidance -> escalation_procedure + matrix + runbook
- scorer improved with normalized lexical/title/section boosts
- evaluator section-title matching normalized to handle lowercase + `**...**`
- retrieval pipeline was refactored to consistently use typed row/result objects instead of mixed dict/object handling
- audit sink updated to expose `log_event(...)`

## Important known issue history

These were already hit and fixed:
- Python 3.9 incompatibility with `@dataclass(slots=True)`
- wrong interpreter / missing `psycopg`
- missing `SUPABASE_DB_URL`
- bad Supabase DSN / wrong connection format
- embedding dimension mismatch (1536 vs 16)
- service/policy/filter/audit contract mismatches
- scorer expecting dicts while repository returned objects
- ingestion runner using `embed()` while real embedder exposed `embed_texts()`
- config wiring accidentally passing descriptors instead of instance values
- OpenAI `insufficient_quota` error when no usable API quota was available

## Current blocker / immediate next step

Most recent goal:
- complete ingestion using the real OpenAI embedding model
- then rerun retrieval eval against real embeddings

If ingestion fails again, first check:
- `OPENAI_API_KEY`
- API quota / billing
- that `model` passed into OpenAI embeddings is a real string value
- that retrieval and ingestion both use the same embedding config

## Commands commonly used

Activate venv:
```bash
source .venv/bin/activate
```

Run ingestion:
```bash
python -m app.ingestion.runner --corpus-root ./corpus
```

Run retrieval eval:
```bash
python3 scripts/run_retrieval_eval.py --mode adapter
```

Check retrieval report:
```bash
cat retrieval_eval_report.json
```

Check ingestion report:
```bash
cat artifacts/ingestion_report.json
```

## Recommended next priorities

1. Complete real-embedding ingestion successfully
2. Rerun retrieval eval on real embeddings
3. Lock that report as the real semantic retrieval baseline
4. Improve section precision and duplicate-result diversity
5. Move to answer generation with citations over retrieved context
6. Then connect tool-backed response generation for structured lookups and incident summaries

## Guidance for the next AI assistant

Do not spend more time on broad architecture rewriting unless requirements change.

Prefer working in this order:
- get real embeddings fully working
- validate retrieval with the existing eval set
- improve section precision
- improve final result diversity
- move to citation-grounded answer generation

Avoid:
- adding more infrastructure complexity
- adding new connectors
- re-expanding route doc types without evidence
- tuning based on dummy-embedding results
