# Demo Walkthrough

## What This Project Demonstrates

- governed AI assistance
- retrieval + structured tools in one API
- approval-gated escalation workflows
- persistent audit and runtime traces
- a private hosted demo path instead of a toy local-only project

## Fast Review Paths

### Path A — Hosted API review

1. Open the hosted base URL.
2. Confirm the landing page points you to:
   - `/docs`
   - `/health`
   - `/ready`
3. Open the hosted `/docs`.
4. Authenticate with:
   - username:
     - `demo`
   - password:
     - the shared `DEMO_ACCESS_PASSWORD`
5. Try these flows:
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

### Hosted Review Path

- step 1:
  - open the base URL
- step 2:
  - verify the landing response explains auth and next steps
- step 3:
  - open `/docs`
- step 4:
  - authenticate with the shared demo password
- step 5:
  - run:
    - one policy query
    - one inventory lookup
    - one incident summary
    - one approval flow
- step 6:
  - if anything looks off, run the hosted smoke script

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

## Password Gate Notes

- local FastAPI:
  - set `DEMO_ACCESS_PASSWORD` in `.env.local`
  - restart the API after changing it
- hosted FastAPI:
  - rotate the platform secret
  - redeploy or restart the app
- local Streamlit against hosted FastAPI:
  - update `.env.local` or the sidebar password field
  - reload the page after rotation

## Screenshot Placeholders

- add current images under:
  - `docs/screenshots/streamlit-ui.png`
  - `docs/screenshots/openapi-docs.png`
  - `docs/screenshots/approval-flow.png`

These should be refreshed after the real hosted deployment is up.

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
