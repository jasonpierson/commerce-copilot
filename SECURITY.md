# Security

This project is currently optimized for local development and controlled smoke testing. A public GitHub repo does **not** automatically expose the application, but a public deployment without hardening would be risky.

## Current Posture

- Secrets are expected to live in `.env.local`, which should stay out of git.
- The local FastAPI server is only reachable if you run it on a machine and expose a port.
- Demo seed data is synthetic, but approval smoke tests can create live rows in the connected database.
- Application tables live in the private `app_private` schema rather than `public`.
- The FastAPI backend owns DB access for those tables; browser/client code does not query them directly.
- Supabase Data API access for app tables is intentionally not part of the architecture.
- RLS is intentionally not applied yet because direct client exposure to those tables has been removed.
- `DEMO_ACCESS_PASSWORD`, when set, gates every non-`/health` API route.
- rotating the demo password means:
  - update the env var
  - restart or redeploy the API
  - tell reviewers to refresh their local UI/client config
- The recommended public-review shape is API hosted, Streamlit local-only.

## Deployment-Hardening Checklist

Use this list before exposing the API behind a public hostname.

### 1. Authentication
- Require authentication on every route, including `/api/v1/query`.
- Keep the demo password gate as a lightweight outer layer, not the final auth system.
- Prefer short-lived bearer tokens or session-backed auth from a trusted identity provider.
- Split operator/admin permissions from read-only analyst permissions.
- Treat approval decision routes as higher-sensitivity actions and require stronger role checks.

### 2. Authorization
- Enforce least privilege at the API layer and, where practical, at the database layer.
- Limit who can create, approve, reject, or browse approvals.
- Restrict incident and inventory reads if production data is sensitive.
- Review service credentials so the app cannot do more than it needs.

### 3. Rate Limits
- Current baseline:
  - in-memory limiter for `POST /api/v1/query`
  - in-memory limiter for:
    - `POST /api/v1/escalations`
    - `POST /api/v1/approvals/{approval_id}/decision`
  - clear `429` responses with `Retry-After`
- Still recommended next:
  - move rate limiting to a gateway or shared store before real public traffic
  - add stronger per-user and per-token controls
  - add alerting around repeated abuse
- Tight limits should stay on mutation routes like:
  - `POST /api/v1/escalations`
  - `POST /api/v1/approvals/{approval_id}/decision`

### 4. CORS
- Keep CORS closed by default.
- If you add a browser client, allow only known frontend origins.
- Avoid wildcard origins on authenticated routes.
- Recheck CORS rules separately for local, staging, and production.

### 5. Logging and Auditability
- Log authentication failures, authorization failures, and rate-limit events.
- Keep approval request/decision audit trails enabled.
- Redact secrets, tokens, and sensitive payload fields from logs.
- Add request IDs and propagate them through API logs for incident debugging.

### 6. Secrets and Config
- Never commit `.env.local`, API keys, or database URLs.
- Rotate keys used for demos if they were ever exposed.
- Use separate credentials for local, staging, and production.
- Prefer a managed secret store over flat env files in deployed environments.

### 7. Network and Runtime Controls
- Put the API behind HTTPS.
- Prefer a reverse proxy or API gateway that can enforce auth and rate limits.
- Restrict inbound access to trusted callers when possible.
- Disable debug settings and verbose exception output in production.

### 8. Database Safety
- Use least-privilege DB credentials.
- Keep application tables in a private schema such as `app_private`.
- Keep approval/demo cleanup scripts restricted to trusted operators.
- Review row-level protections if this moves to multi-tenant or mixed-sensitivity data.
- Back up approval and audit tables before destructive maintenance workflows.

## Operator Safety Notes

- Use disposable approval requests for live smoke tests.
- After live approval tests, run approval-only cleanup:

```bash
source .venv/bin/activate
set -a
source .env.local
set +a
python -m scripts.cleanup_demo_data --scope approvals --apply
```

- Prefer full cleanup only when you intentionally want to reset seeded operational data.

## Security Reporting

If this project is deployed publicly in the future, add a dedicated reporting contact and response policy here.

## Demo-Only vs Production

This repository uses mock/demo auth headers and a backend-only exposure model during development. Before any public deployment:

- shared password gate is demo-only, not real identity
- Replace mock headers with a real identity provider and token validation
- Add per-user/token rate limits on `/api/v1/query` and approval endpoints
- Enforce least-privilege authorization tied to real identities
- Move secrets to a managed store and rotate any demo keys
- Harden CORS and network ACLs; disable verbose errors in production
