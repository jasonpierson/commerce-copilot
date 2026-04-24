# Demo Walkthrough

## What This Project Demonstrates

- governed AI assistance
- retrieval + structured tools in one API
- approval-gated escalation workflows
- persistent audit and runtime traces
- a private hosted demo path instead of a toy local-only project

## Fast Review Paths

### Path A — Hosted API review

1. Open the hosted `/docs`.
2. Authenticate with:
   - username:
     - `demo`
   - password:
     - the shared `DEMO_ACCESS_PASSWORD`
3. Try these flows:
   - `POST /api/v1/query`
     - policy question
   - `POST /api/v1/query`
     - inventory lookup
   - `POST /api/v1/query`
     - incident summary
   - `POST /api/v1/escalations`
     - create approval
   - `GET /api/v1/approvals/{approval_id}`
   - `POST /api/v1/approvals/{approval_id}/decision`

### Path B — Local UI review

```bash
make install
make seed
make run-api
make ui
```

Or point the UI at a hosted API:

```bash
GCOP_API_BASE="https://<your-host>.koyeb.app" make ui
```

## Suggested Query Prompts

- `What is the return process for damaged products?`
- `Check inventory for the Phantom X shoes.`
- `Summarize incident INC-1091 and tell me the likely customer impact.`
- `Should INC-1091 be escalated right now?`
- `Show me the approval dashboard.`
- `Which approver is the bottleneck?`

## Architecture Decisions

- retrieval stays focused on narrative guidance:
  - policies
  - SOPs
  - runbooks
- structured reads answer exact operational state:
  - inventory
  - incidents
  - approvals
- escalation is governed:
  - suggested in query flows
  - executed only through approval endpoints
- hosted-demo safety is layered:
  - demo password gate
  - lightweight rate limiting
  - readiness checks
  - JSON stdout logging

## Known Limitations

- demo auth is not real production identity
- rate limiting is in-memory, not distributed
- Streamlit is a reviewer convenience layer, not the product frontend
- approval notifications and orchestration are still stubbed
- hosted smoke tests can create disposable approval records unless skipped
