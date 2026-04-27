# Hosted Demo v1

## Milestone Summary

- live Koyeb-hosted FastAPI demo
- password-protected reviewer access
- retrieval-backed policy/process guidance
- structured incident and inventory lookups
- approval-gated escalation workflow
- audit logs, request tracing, and hosted smoke verification

## Included In This Release

- hosted API root, health, readiness, and version surfaces
- interactive API docs at `/docs`
- `/api/v1/query` for:
  - policy/process Q&A
  - incident summaries
  - escalation guidance
  - approval analytics questions
- approval workflow endpoints for:
  - create
  - status
  - decision
  - audit
  - dashboard views
- reviewer documentation, screenshots, and release checklist

## Demo-Only By Design

- shared demo password instead of production auth
- seeded operational data
- mock auth headers for role simulation
- lightweight in-memory rate limiting
- Streamlit as a local-only reviewer companion

## How Reviewers Access It

- hosted URL:
  - `https://harsh-juieta-jasons-org-14a2695f.koyeb.app/`
- first clicks:
  - `/`
  - `/docs`
  - `/version`
- password:
  - shared out-of-band by the maintainer
- maintainer review path:
  - terminal examples in `docs/api-review/curl-examples.md`
  - Postman collection in `docs/api-review/postman_collection.json`

## What The Screenshots Show

- `docs/screenshots/openapi-overview.png`
  - hosted API surface and interactive docs
- `docs/screenshots/openapi-query-example.png`
  - live query workflow in Swagger UI
- `docs/screenshots/approval-flow.png`
  - governed approval response shape
- `docs/screenshots/streamlit-ui.png`
  - local reviewer UI against the same backend

## Hosted Trust Signals

- live hosted URL is documented in the repo
- `X-Request-Id` is returned on core API routes
- hosted smoke automation exists in GitHub Actions
- `/version` exposes deployed build metadata

## Future Work

- production identity and authorization
- distributed rate limiting
- operator-facing frontend beyond Streamlit
- notificationing and workflow orchestration
- stronger deployment automation and environment separation
