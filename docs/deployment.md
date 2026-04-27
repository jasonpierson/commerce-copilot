# Deployment Path

## Authoritative Hosted Path

- platform:
  - Koyeb
- hosted component:
  - FastAPI API only
- local-only component:
  - Streamlit demo UI
- repository deployment source of truth:
  - `koyeb.yaml`
  - `Dockerfile`

## Why This Is The Recommended Path

- one real hosted surface instead of multiple half-supported options
- Docker-based deployment keeps the runtime reproducible
- `/docs` becomes the main hosted review surface
- Streamlit stays local so the public footprint stays small

## Hosting Files

- `koyeb.yaml`
  - repo-local deployment manifest and settings source of truth
- `Dockerfile`
  - immutable production-lite image
- `.dockerignore`
  - trims the build context

## Required Runtime Env

- plaintext:
  - `APP_ENV=production`
  - `APP_HOST=0.0.0.0`
  - `APP_PORT=8000`
  - `DB_APP_SCHEMA=app_private`
- secrets:
  - `OPENAI_API_KEY`
  - `SUPABASE_DB_URL`
  - `DEMO_ACCESS_PASSWORD`

## Optional Build Metadata Env

- `APP_VERSION`
- `GIT_SHA`
- `BUILD_TIMESTAMP`

Use these so `/version` can tell you exactly which deploy Koyeb is serving.

Recommended values per deploy:

- `APP_VERSION`
  - release tag or package version such as `0.1.0`
- `GIT_SHA`
  - short commit SHA for the deployed commit
- `BUILD_TIMESTAMP`
  - UTC ISO-8601 timestamp for the deploy or image build

Practical Koyeb pattern:

- update these env vars when you cut a new hosted release
- redeploy immediately after updating them
- confirm the result at:
  - `/version`
- source of truth for expected values:
  - `koyeb.yaml`

Current expectation:

- release tag, `/version`, and hosted deploy metadata should line up
- if `/version` still shows `unknown`, treat the deploy as not fully packaged yet

## Health Model

- `GET /health`
  - liveness only
  - use when you only want to know the process is up
- `GET /ready`
  - readiness
  - required config present
  - DB connectivity succeeds
- `GET /version`
  - deployed build metadata
  - app version, git SHA, build timestamp, and `APP_ENV`

Recommended Koyeb health check:
- protocol:
  - HTTP
- path:
  - `/ready`

Reference docs used:
- Koyeb FastAPI deploy guide:
  - https://www.koyeb.com/docs/deploy/fastapi
- Koyeb health checks:
  - https://www.koyeb.com/docs/run-and-scale/health-checks
- Koyeb exposing services:
  - https://www.koyeb.com/docs/build-and-deploy/exposing-your-service

## Koyeb Deploy Sequence

## Current Hosted Demo URL

- current hosted demo URL:
  - `https://harsh-juieta-jasons-org-14a2695f.koyeb.app/`
- auth:
  - Basic auth username: `demo`
  - password shared out-of-band by the maintainer

### Option A — Control panel

1. Create a new Koyeb app.
2. Connect the GitHub repo.
3. Choose Dockerfile-based build.
4. Mirror the values from `koyeb.yaml`:
   - service name
   - port `8000`
   - route `/`
   - HTTP health check path `/ready`
   - runtime env vars
5. Set secrets:
   - `OPENAI_API_KEY`
   - `SUPABASE_DB_URL`
   - `DEMO_ACCESS_PASSWORD`
6. Deploy.
7. After the deployment turns healthy, run the remote smoke script.
8. Verify `/version` so you know which build Koyeb actually deployed.

## Post-Deploy Validation Checklist

- confirm the app is reachable
- confirm:
  - `GET /health` -> `200`
  - `GET /ready` -> `200`
- confirm password gate:
  - `POST /api/v1/query` without password -> `401`
  - same request with password -> `200`
- confirm build metadata:
  - `GET /version` -> `200`
- run:
  - `python scripts/smoke_remote_demo.py`
- inspect logs by `request_id`
- verify one approval request + decision flow
- if the deploy is bad:
  - roll back to the previous working Git commit in Koyeb
  - rerun the smoke script

Latest successful live validation:
- date:
  - `2026-04-24`
- result:
  - hosted smoke succeeded end to end against the live Koyeb URL

### Option B — CLI-assisted settings

Use the values in `koyeb.yaml` together with the CLI flags documented by Koyeb:
- `--git-builder docker`
- `--port 8000:http`
- `--route /:8000`
- `--checks 8000:http:/ready`
- `--env APP_ENV=production`
- `--env APP_HOST=0.0.0.0`
- `--env APP_PORT=8000`
- `--env DB_APP_SCHEMA=app_private`

## Docker Runtime Notes

- image is built as an immutable wheel install
- image does not use `pip install -e .`
- runtime user is non-root
- only runtime-required files are copied into the final image:
  - installed package
  - `scripts/run_api.py`

Local verification:

```bash
docker build -t commerce-ops-copilot .
docker run --rm -p 8000:8000 --env-file .env.local commerce-ops-copilot
```

## Startup Validation

Production startup validates required env vars before boot:
- `SUPABASE_DB_URL`
- `OPENAI_API_KEY`

If any are missing:
- startup exits clearly in production mode
- `/ready` also reports the missing configuration

Readiness additionally expects:
- `DEMO_ACCESS_PASSWORD`

## Rate Limiting

The hosted demo includes lightweight in-memory limits for:
- `POST /api/v1/query`
- `POST /api/v1/escalations`
- `POST /api/v1/approvals/{approval_id}/decision`

Defaults:
- query:
  - `30` requests / `60` seconds
- approval mutations:
  - `10` requests / `60` seconds

Tune with env vars:
- `QUERY_RATE_LIMIT_MAX_REQUESTS`
- `QUERY_RATE_LIMIT_WINDOW_SECONDS`
- `APPROVAL_RATE_LIMIT_MAX_REQUESTS`
- `APPROVAL_RATE_LIMIT_WINDOW_SECONDS`

## Hosted Smoke Test

After deployment:

```bash
source .venv/bin/activate
set -a
source .env.local
set +a
GCOP_API_BASE="https://harsh-juieta-jasons-org-14a2695f.koyeb.app/" python scripts/smoke_remote_demo.py
```

What it checks:
- `/health`
- `/ready`
- policy query
- inventory lookup
- incident summary
- disposable approval flow by default

Cold-start note:
- the first hosted smoke run may need a longer timeout while the Koyeb service wakes up
- if needed, retry with:

```bash
GCOP_API_BASE="https://harsh-juieta-jasons-org-14a2695f.koyeb.app/" python scripts/smoke_remote_demo.py --timeout 90
```

If you want a non-mutating run:

```bash
GCOP_API_BASE="https://harsh-juieta-jasons-org-14a2695f.koyeb.app/" python scripts/smoke_remote_demo.py --skip-approval-flow
```

Convenience target for the live deployment:

```bash
make smoke-remote-live
```

## Scheduled Hosted Smoke

- workflow:
  - `.github/workflows/hosted-smoke.yml`
- triggers:
  - `workflow_dispatch`
  - weekday schedule
- required GitHub Actions secrets:
  - `GCOP_API_BASE`
  - `DEMO_ACCESS_PASSWORD`
- safety:
  - the workflow uses `--skip-approval-flow`
  - the shared password is never printed in logs
- outputs:
  - GitHub step summary
  - `hosted-smoke-results` artifact with summary + JSON results

## Optional Custom Domain

- current state:
  - the Koyeb URL is acceptable for the hosted demo
- later option:
  - add a custom subdomain only if you actually plan to keep the demo live long-term

## Debugging A Bad Hosted Response

- step 1:
  - rerun the failing request and capture `request_id`
- step 2:
  - inspect platform logs for:
    - `stream=query`
    - `stream=retrieval`
    - `stream=approval`
- step 3:
  - correlate by `request_id`
- step 4:
  - if reproducing locally, use:

```bash
python scripts/inspect_logs.py --trace-request <request_id>
```

## Log Strategy

- local development:
  - JSONL artifacts in `artifacts/`
  - inspect with `scripts/inspect_logs.py`
- hosted deployment:
  - the same events are also emitted to stdout as JSON
  - use platform/container logs for live debugging

## Streamlit Position

- local-only reviewer helper
- not part of the hosted deployment contract
- can point at the hosted API with:
  - `GCOP_API_BASE=https://harsh-juieta-jasons-org-14a2695f.koyeb.app/`

## Related Docs

- `README.md`
- `SECURITY.md`
- `docs/architecture.md`
- `docs/demo.md`
- `docs/release-checklist.md`
