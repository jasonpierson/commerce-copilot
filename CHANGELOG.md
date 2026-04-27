# Changelog

This changelog tracks project evolution from the first commit, `c2ea3da` (`initial commit`), through the current working tree.

## Unreleased

### Added
- `docs/maintainer-runbook.md` for demo password rotation, Koyeb/GitHub secret upkeep, redeploy steps, smoke validation, and log inspection
- `docs/api-review/README.md`
- `docs/api-review/curl-examples.md`
- `docs/api-review/postman_collection.json`
- `GET /version` for deployed build metadata:
  - app version
  - git SHA
  - build timestamp
  - `APP_ENV`
- `.github/workflows/hosted-smoke.yml` for manual and scheduled live hosted smoke checks
- `docs/releases/hosted-demo-v1.md` as the shareable hosted-demo milestone note
- `docs/release-checklist.md` for low-stress hosted demo updates
- `scripts/verify_env.py` for startup/readiness env checks before deploy
- richer root landing response for hosted reviewers
- canonical screenshot set under `docs/screenshots/`
- `koyeb.yaml` as the repo deployment source of truth for the hosted demo
- `GET /ready` for config + DB readiness checks alongside `GET /health`
- lightweight in-memory rate limiting for hosted query and approval mutation routes
- `scripts/smoke_remote_demo.py` for post-deploy hosted smoke verification
- `tests/test_deployment_contract.py` for hosted-demo contract coverage
- `docs/demo.md` as a short review/demo walkthrough
- Demo password protection for the API and Streamlit UI using `DEMO_ACCESS_PASSWORD`
- `scripts/inspect_logs.py` for reviewer-friendly inspection of query, approval, and retrieval traces
- GitHub Actions CI workflow for compile + unit test coverage
- Declarative route-rule structure plus route-specific handlers in `app/api/query_service.py`
- Persistent application trace logs:
  - `artifacts/query_events.jsonl`
  - `artifacts/approval_events.jsonl`
- Explicit mock auth helpers using:
  - `X-User-Id`
  - `X-User-Role`
- `Makefile` starter commands for install, run, seed, demo, eval, test, and cleanup
- `docs/architecture.md`
- `docs/deployment.md`
- Focused query-service extraction tests in `tests/test_query_service.py`
- Pending-approval owner answers in `/api/v1/query`, including incident-scoped questions like `Who is holding the pending approvals for INC-1091?`
- Dashboard filters for `incident_code` and `requester`
- Dashboard metrics for:
  - pending approval count
  - approvals created in the last 24 hours
  - approvals decided in the last 24 hours
  - oldest pending approval age in minutes
  - pending approvals by priority
  - pending approvals by current approver
  - pending approvals by incident
- Root-level documentation:
  - `README.md`
  - `CHANGELOG.md`
- Escalation-load answers in `/api/v1/query`, including questions like `Which incidents have the most pending approval pressure?`
- Requester-load answers in `/api/v1/query`, including questions like `Who is holding the pending approvals?` and `Which requester is creating the most approval load?`
- A lightweight operator runbook section in `README.md` for smoke tests and cleanup flows
- Basic auth/rate-limit recommendations in `README.md` for future public deployment
- Approver-bottleneck answers in `/api/v1/query`, including questions like `Which approver is the bottleneck?`
- Oldest-pending approval answers in `/api/v1/query`, including questions like `Which approver has the oldest pending item?`
- Oldest-pending incident answers in `/api/v1/query`, including questions like `Which incident has the oldest pending approval?`
- Oldest-pending requester answers in `/api/v1/query`, including questions like `Which requester has the oldest pending approval?`
- Age-threshold incident lookup answers in `/api/v1/query`, including questions like `Show me only incidents with pending approvals older than 30 minutes`
- 7-day dashboard metrics for approvals created and decided
- 7-day per-day approval trend buckets and oldest-pending-item metrics on the approval dashboard
- Dedicated `SECURITY.md` deployment-hardening checklist for auth, rate limits, CORS, logging, and secret handling
- A compact operator analytics section in `README.md` with example approval-ops prompts
- `GET /api/v1/approvals/dashboard/summary` for headline metrics plus top risks first
- `GET /api/v1/operator/dashboard` as a UI-oriented operator dashboard shape

### Changed
- top-of-README reviewer guidance now includes status, access, terminal-first review, and maintainer contact flow
- release docs now point to terminal and machine-readable API review assets
- deployment docs now explain how to keep `/version` meaningful in Koyeb by updating build metadata env vars
- core API routes now return `X-Request-Id` response headers alongside the existing response-body field
- reviewer docs now explain that demo access is shared out-of-band and that the password is never committed
- deployment docs now describe `/version`, hosted smoke workflow secrets, and the optional custom-domain path
- docs now separate more explicitly:
  - demo password gate vs real auth
  - mock headers vs real identity
  - in-memory limits vs production rate limiting
- deployment docs now include:
  - current hosted URL
  - post-deploy validation checklist
  - request-id based hosted debugging flow
- remote smoke now checks:
  - root landing behavior
  - missing-password rejection
- screenshots are now embedded directly in:
  - `README.md`
  - `docs/demo.md`
- screenshot naming is now stable and descriptive:
  - `landing-page.png`
  - `openapi-overview.png`
  - `openapi-query-example.png`
  - `approval-flow.png`
  - `streamlit-ui.png`

## 2026-04-24 — First Hosted Private Demo Milestone

### Added
- Live hosted demo URL documented across:
  - `README.md`
  - `docs/deployment.md`
  - `docs/release-checklist.md`
- `make smoke-remote-live` for low-friction live verification

### Changed
- Live Koyeb hosted smoke validation succeeded end to end on `2026-04-24`
- manual hosted reviewer pass succeeded end to end on `2026-04-24`
- Hosted reviewer docs now match the actual landing page and `/docs` experience
- Root landing response now calls out that Streamlit is local-only
- `Dockerfile` is now a production-lite non-root immutable runtime image
- local and hosted logs now share a more consistent JSON event shape, with hosted events emitted to stdout
- `README.md` and `docs/deployment.md` now describe the concrete Koyeb deployment path, readiness semantics, hosted smoke testing, and review flow
- `scripts/run_api.py` now respects `APP_ENV`, `APP_HOST`, and `APP_PORT`
- `Dockerfile` now launches through `scripts/run_api.py`
- Deployment docs now define Koyeb-hosted API + local-only Streamlit as the authoritative demo path
- `/api/v1/query` orchestration is now split into cleaner route handlers instead of one large branch-heavy method
- Approval create/decision flows now persist request-trace artifacts to disk
- Approval and query routers now resolve the acting demo principal from headers before applying workflow logic
- `scripts/demo_queries.py` now uses the mock auth headers and includes escalation guidance in the golden path
- `README.md` now includes:
  - a 2-minute demo
  - enterprise-focused positioning
  - real vs mock vs future-work boundaries
  - Make-based local run instructions
- `/api/v1/query` dashboard responses now return grouped dashboard buckets plus structured dashboard metrics
- Approval list and dashboard service methods now support requester-aware filtering
- Dashboard metrics now report both 24-hour and 7-day approval activity windows
- Dashboard-style `/api/v1/query` answers now render 7-day trend buckets as a clearer line-by-line summary
- `README.md` now links to `SECURITY.md` near the top for easier visibility
- Approval analytics now expose requester context on oldest-pending approval items
- Dashboard summary answers now surface top-risk headlines directly in the returned summary text

## 2026-04-20 — `76ccb5d` — Expand approval browsing and dashboard APIs

### Added
- Incident-specific approval list questions in `/api/v1/query`, such as `Show me rejected approvals for INC-1091`
- Pagination and sorting support for `GET /api/v1/approvals`
- `GET /api/v1/approvals/dashboard` grouped by approval status
- Dashboard-style `/api/v1/query` support for `Show me the approval dashboard`

### Changed
- Approval browsing matured from simple filtered lists to list + dashboard operational views
- API test coverage expanded for dashboard and incident-filtered approval browsing

## 2026-04-20 — `3a8bc90` — Expand approval query and browsing workflows

### Added
- `/api/v1/query` support for:
  - explicit rejection reasons from audit notes
  - incident approval history requests
  - approval list browsing such as `Show me all pending approvals`
- `GET /api/v1/approvals` list endpoint with initial filtering

### Changed
- Approval list responses gained structured approval collections and links back to approval APIs

## 2026-04-20 — `0572582` — Add approval audit filters and escalation status queries

### Added
- Audit endpoint filtering by `event_type`
- `/api/v1/query` support for incident escalation-status questions such as whether an incident has already been escalated

### Changed
- Approval audit history became easier to inspect for request-vs-decision views

## 2026-04-20 — `f58f3ca` — Add approval audit and linked incident context

### Added
- `GET /api/v1/approvals/{approval_id}/audit`
- Approval audit event modeling and lookup in the service layer
- Incident summaries that surface linked approval state and related links
- Approval-history style answers in `/api/v1/query`

## 2026-04-20 — `4fb434f` — Add approval lookup summaries to query API

### Added
- Natural-language approval lookup answers such as:
  - `Who approved approval ...?`
  - `Who rejected approval ...?`
- Structured approval payloads in `/api/v1/query` responses

## 2026-04-20 — `359db0e` — Add approval-only cleanup mode

### Added
- `scripts/cleanup_demo_data.py --scope approvals`
- Approval-only cleanup path that removes approval workflow artifacts without touching seeded catalog/incident data

## 2026-04-20 — `bf81d5b` — Remove tracked Python cache artifacts

### Changed
- Removed tracked `__pycache__` and other Python cache noise from git history going forward

## 2026-04-20 — `84443e9` — Add approval guardrails and query follow-up links

### Added
- Permission-failure and duplicate-decision API tests
- Query response links to incident details and approval actions
- Approval suggestions in relevant incident query responses
- Cleanup/admin utility for seeded demo data management

### Changed
- Approval decision handling now cleanly distinguishes permission failures from validation errors

## 2026-04-20 — `5aaee5e` — Add incident detail and approval workflow endpoints

### Added
- `GET /api/v1/incidents/{incident_code}`
- Approval workflow endpoints:
  - `POST /api/v1/escalations`
  - `GET /api/v1/approvals/{approval_id}`
  - `POST /api/v1/approvals/{approval_id}/decision`
- Approval persistence, decision flow, and audit writes
- Seeded demo users to support requester/approver workflows
- API tests for inventory, incident detail, incident summary, and escalation flow

## 2026-04-20 — `cbe54e8` — Fix retrieval quality and add seeded domain data workflows

### Added
- Demo seed data for:
  - users
  - products
  - locations
  - inventory
  - incidents
  - incident events
- Hybrid incident summary path using structured incident data plus retrieval context
- First structured inventory lookup path
- Shared DB service helpers for API data access

### Changed
- Retrieval quality improved with updated scoring/profile behavior
- Query stack evolved beyond pure retrieval into a hybrid structured + retrieval API

## 2026-04-20 — `31cb655` — Delete .DS_Store

### Changed
- Removed tracked macOS metadata files from the repo

## 2026-04-20 — `23b81f8` — ignore files

### Changed
- Expanded ignore rules for local/dev-only files

## 2026-04-20 — `3d6ae11` — remove unused markdown files

### Changed
- Removed stale markdown artifacts from the early scaffold phase

## 2026-04-20 — `c2ea3da` — initial commit

### Added
- Initial ingestion scaffold
- Retrieval evaluation layout
- Early project packaging via `pyproject.toml`
- Base repository structure for:
  - ingestion
  - retrieval
  - scripts

### Initial Focus
- building the corpus ingestion pipeline
- evaluating retrieval quality over a governed operations dataset
