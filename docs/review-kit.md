# Review Kit

## What To Open First

- hosted URL:
  - `https://harsh-juieta-jasons-org-14a2695f.koyeb.app/`
- then:
  - `/`
  - `/version`
  - `/docs`

## How Access Works

- the URL is public in the repo
- the password is shared out-of-band by the maintainer
- no secret values are committed to the repo

## Best Screenshots

- `docs/screenshots/openapi-overview.png`
- `docs/screenshots/openapi-query-example.png`
- `docs/screenshots/approval-flow.png`

## Best 2-Minute Review Path

- open the hosted root page
- check `/version`
- open `/docs`
- run:
  - one policy query
  - one inventory lookup

## Best 5-Minute Technical Review Path

- run the hosted API review path in `/docs`
- inspect:
  - `/api/v1/query`
  - `/api/v1/escalations`
  - `/api/v1/approvals/{approval_id}`
  - `/api/v1/approvals/{approval_id}/decision`
- note the response-level:
  - `X-Request-Id`
- review supporting docs:
  - `docs/demo.md`
  - `docs/deployment.md`
  - `docs/maintainer-runbook.md`

## Key Differentiators

- governed actions
  - escalation is approval-gated
- retrieval + tools
  - narrative answers plus structured lookups
- approvals
  - status, decision, audit, dashboard
- auditability
  - request tracing and approval history
- release / ops discipline
  - hosted smoke workflow
  - deployment docs
  - release note

## Useful Companion Assets

- terminal examples:
  - `docs/api-review/curl-examples.md`
- machine-readable collection:
  - `docs/api-review/postman_collection.json`
- release note:
  - `docs/releases/hosted-demo-v1.md`
