# Changelog

This changelog tracks project evolution from the first commit, `c2ea3da` (`initial commit`), through the current working tree.

## Unreleased

### Added
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
- 7-day dashboard metrics for approvals created and decided
- Dedicated `SECURITY.md` deployment-hardening checklist for auth, rate limits, CORS, logging, and secret handling

### Changed
- `/api/v1/query` dashboard responses now return grouped dashboard buckets plus structured dashboard metrics
- Approval list and dashboard service methods now support requester-aware filtering
- Dashboard metrics now report both 24-hour and 7-day approval activity windows

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
