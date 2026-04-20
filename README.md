# CommerceOpsCopilot

Governed Commerce Operations Copilot is a Python/FastAPI prototype for a support-facing copilot that blends:

- retrieval over a curated operations corpus
- structured lookups over operational tables
- approval-gated escalation workflows
- lightweight operational analytics over approval load

The project started as an ingestion/retrieval scaffold and has grown into a working backend slice for policy Q&A, incident support, inventory lookup, and approval workflow operations.

## Current Status

### Implemented
- Retrieval-backed `policy_qa`, `incident_summary`, and `escalation_guidance`
- Structured inventory lookup from seeded `products`, `inventory`, and `locations`
- Incident detail and incident timeline endpoints
- Approval request, status, decision, audit, list, and dashboard endpoints
- `/api/v1/query` support for:
  - policy/process questions
  - incident summaries
  - escalation guidance
  - approval status/history/rejection reason questions
  - approval browsing and dashboard questions
  - pending-approval owner questions
- escalation-load / approval-pressure questions
- Demo seeding and cleanup scripts for local/live development
- API test coverage for the main approval, inventory, and incident flows

### Not Implemented Yet
- frontend/UI
- authentication/authorization beyond demo role assumptions
- production-grade approval notifications or workflow orchestration
- incident/approval analytics beyond the current dashboard metrics
- deployment packaging and infra automation

## Architecture

```text
app/
  api/
    main.py                FastAPI app assembly
    query_router.py        /api/v1/query entrypoint
    query_service.py       Route classification and response orchestration
    incident_router.py     Incident detail endpoint
    incident_service.py    Incident DB access
    inventory_service.py   Product + inventory DB access
    approval_router.py     Approval workflow endpoints
    approval_service.py    Approval + audit DB access
    db.py                  Shared Postgres connection helpers
    schemas.py             Pydantic response/request models

  retrieval/
    runtime.py             Retrieval service wiring
    service.py             Retrieval orchestration
    scorer.py              Post-retrieval scoring/reranking
    repository.py          Vector retrieval repository
    config.py              Retrieval tuning from env
    evals/                 Retrieval evaluation set + evaluator

  ingestion/
    runner.py              Ingestion entrypoint
    loader.py              Corpus loading
    normalizer.py          Text normalization
    chunker.py             Chunk creation
    segmenter.py           Segmentation helpers
    embedder.py            Ingestion embeddings
    repository.py          Ingestion persistence
    report.py              Ingestion reporting

  common/
    config.py              Shared embedding config
    embeddings.py          OpenAI embedder

scripts/
  run_api.py               Starts FastAPI app
  run_ingestion.py         Runs ingestion pipeline
  run_retrieval_eval.py    Runs retrieval evaluation
  run_retrieval_smoke_test.py
  seed_domain_data.py      Seeds demo users/catalog/incidents
  cleanup_demo_data.py     Cleans demo data or approval-only artifacts
```

## Core Concepts

### 1. Retrieval Layer
The retrieval subsystem answers policy/process questions and supports incident/escalation guidance.

Key properties:
- vector search against Postgres-backed retrieval data
- route-aware post-retrieval scoring
- per-route chunk caps for precision/diversity balance
- evaluation harness with a JSONL eval set and adapter mode

Primary files:
- `app/retrieval/runtime.py`
- `app/retrieval/service.py`
- `app/retrieval/scorer.py`
- `app/retrieval/evals/evaluator.py`
- `scripts/run_retrieval_eval.py`

### 2. Structured Operational Data
The API uses structured tables for live answers where retrieval alone is not enough.

Current structured domains:
- inventory and catalog
- incidents and incident timelines
- approvals and approval audit history
- demo users/approvers

Primary files:
- `app/api/inventory_service.py`
- `app/api/incident_service.py`
- `app/api/approval_service.py`
- `scripts/seed_domain_data.py`

### 3. `/api/v1/query` as the Main Copilot Entry Point
`/api/v1/query` classifies the user message into a route and then composes retrieval, structured data, links, and approval suggestions into one response.

Representative route types:
- `policy_qa`
- `structured_lookup`
- `incident_summary`
- `escalation_guidance`

Primary files:
- `app/api/query_router.py`
- `app/api/query_service.py`

## API Surface

### Health
- `GET /health`

### Unified Query
- `POST /api/v1/query`

### Incident Endpoints
- `GET /api/v1/incidents/{incident_code}`

### Approval Endpoints
- `POST /api/v1/escalations`
- `GET /api/v1/approvals`
- `GET /api/v1/approvals/dashboard`
- `GET /api/v1/approvals/{approval_id}`
- `GET /api/v1/approvals/{approval_id}/audit`
- `POST /api/v1/approvals/{approval_id}/decision`

## Example Query Behaviors

### Policy / Process
```text
What is the escalation policy for severe checkout incidents?
```

### Inventory Lookup
```text
Check inventory for the Phantom X shoes.
```

### Incident Summary
```text
Summarize incident INC-1091 and tell me the likely customer impact.
```

### Approval History
```text
Why was approval <approval_id> rejected?
Show me the approval history for incident INC-1091.
```

### Approval Operations
```text
Show me all pending approvals.
Show me rejected approvals for INC-1091.
Show me the approval dashboard.
Who is holding the pending approvals for INC-1091?
Which incidents have the most pending approval pressure?
```

## Dashboard Metrics

`GET /api/v1/approvals/dashboard` and dashboard-style `/api/v1/query` responses currently expose:

- `pending_count`
- `oldest_pending_age_minutes`
- `pending_by_priority`
- `pending_by_owner`
- `pending_by_incident`

Supported dashboard filters:
- `incident_code`
- `requester`
- `page_size_per_bucket`

## Local Setup

### Requirements
- Python 3.11+
- Postgres/Supabase database with the expected schema
- OpenAI API key for real embeddings/query embedding

### Install
```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e .
```

### Environment
Create `.env.local` in the repo root and keep it out of git.

Typical variables:

```bash
OPENAI_API_KEY=...
SUPABASE_DB_URL=...
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
```

Retrieval tuning is env-driven as well; the retrieval config reads several runtime knobs from environment variables.

## Common Workflows

### Run the API
```bash
source .venv/bin/activate
set -a
source .env.local
set +a
python scripts/run_api.py
```

### Run Ingestion
```bash
source .venv/bin/activate
set -a
source .env.local
set +a
python scripts/run_ingestion.py
```

### Run Retrieval Eval
```bash
source .venv/bin/activate
set -a
source .env.local
set +a
python scripts/run_retrieval_eval.py --mode adapter
```

### Seed Demo Operational Data
```bash
source .venv/bin/activate
set -a
source .env.local
set +a
python scripts/seed_domain_data.py
```

### Cleanup Demo Approval Artifacts Only
```bash
source .venv/bin/activate
set -a
source .env.local
set +a
python -m scripts.cleanup_demo_data --scope approvals --apply
```

### Cleanup Full Demo Operational Data
```bash
source .venv/bin/activate
set -a
source .env.local
set +a
python -m scripts.cleanup_demo_data --scope full --apply
```

## Testing

### Unit/API Tests
```bash
source .venv/bin/activate
python -m unittest discover -s tests -p 'test_*.py' -v
```

Current covered areas include:
- inventory lookups
- incident detail and incident summary flows
- escalation request/decision flows
- approval status/history/audit flows
- approval list/dashboard flows
- `/api/v1/query` approval operations behavior

## Demo Seed Data

The project includes demo operational data for development and smoke testing.

Seeded domains:
- users
- products
- locations
- inventory rows
- incidents
- incident timeline events

Important seeded incident examples:
- `INC-1042` — resolved mobile checkout issue
- `INC-1077` — investigating inventory feed sync delay
- `INC-1091` — mitigated payment authorization timeout

Representative seeded product:
- `PX-100` / `Phantom X Shoes`

## Known Constraints

- This is still a scaffold/prototype, not a production-hardened service
- Database schema management is assumed rather than fully codified in this repo
- Query classification is rule-based and intentionally simple
- The app currently assumes trusted internal usage patterns and demo identities
- Retrieval quality depends on environment tuning and corpus quality
- Audit logging is best-effort in the scaffold

## Files Worth Reading First

If you are new to the repo, start here:
- `README.md`
- `CHANGELOG.md`
- `app/api/query_service.py`
- `app/api/approval_service.py`
- `app/retrieval/service.py`
- `scripts/seed_domain_data.py`
- `tests/test_api.py`

## Project Trajectory

The repo has evolved in roughly this order:

1. ingestion scaffold
2. retrieval evaluation and tuning
3. backend API slice for query/incident/inventory support
4. approval workflow and audit trail
5. approval browsing/dashboard operations layer

The next likely expansion areas are:
- richer cross-incident workload and approval-pressure analytics
- approval queue operations and ownership reporting
- better retrieval/structured orchestration
- UI and operator workflows on top of the API
