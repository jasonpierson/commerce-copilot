# Maintainer Runbook

## What This Runbook Is For

- rotate the hosted demo password
- update Koyeb and GitHub Actions secrets
- redeploy safely
- rerun hosted smoke
- inspect common failures quickly

## Secrets You Own

- Koyeb service env / secrets:
  - `DEMO_ACCESS_PASSWORD`
  - `OPENAI_API_KEY`
  - `SUPABASE_DB_URL`
  - `APP_VERSION`
  - `GIT_SHA`
  - `BUILD_TIMESTAMP`
- GitHub Actions secrets:
  - `GCOP_API_BASE`
  - `DEMO_ACCESS_PASSWORD`

## Rotate The Demo Password

- 1. choose a new password
- 2. update Koyeb:
  - replace `DEMO_ACCESS_PASSWORD`
- 3. update GitHub Actions:
  - replace `DEMO_ACCESS_PASSWORD`
- 4. update local `.env.local`
- 5. redeploy Koyeb
- 6. rerun hosted smoke:
  - `make smoke-remote-live`
- 7. verify:
  - `/`
  - `/docs`
  - `/version`

## Refresh Build Metadata

Before or during deploy, set:

- `APP_VERSION`
  - example: `0.1.0`
- `GIT_SHA`
  - example: current short commit SHA
- `BUILD_TIMESTAMP`
  - example: ISO-8601 UTC timestamp

Why:

- `/version` should distinguish deploys
- reviewers can confirm the hosted app matches the repo state

## Redeploy Checklist

- push the target commit to GitHub
- update Koyeb env vars if needed
- confirm Koyeb still points to:
  - branch:
    - `main`
  - Dockerfile:
    - `Dockerfile`
  - readiness:
    - `/ready`
- redeploy
- wait for healthy status
- run:
  - `make smoke-remote-live`

## GitHub Hosted Smoke Upkeep

- workflow:
  - `.github/workflows/hosted-smoke.yml`
- required secrets:
  - `GCOP_API_BASE`
  - `DEMO_ACCESS_PASSWORD`
- expected behavior:
  - scheduled weekday smoke
  - manual `workflow_dispatch`
  - non-mutating:
    - `--skip-approval-flow`

## Common Failure Map

- `/version` returns `404`
  - likely cause:
    - hosted app has not been redeployed after version-endpoint changes
- `/ready` returns `503`
  - likely cause:
    - missing env var
    - DB connectivity failure
- `/api/v1/query` returns `401`
  - likely cause:
    - stale or mismatched `DEMO_ACCESS_PASSWORD`
- hosted smoke fails only on first run
  - likely cause:
    - Koyeb cold start
  - retry:
    - `python scripts/smoke_remote_demo.py --timeout 90`
- hosted smoke workflow fails in GitHub
  - likely cause:
    - missing or stale Actions secrets

## Reviewer Troubleshooting Matrix

- reviewer gets `401`
  - check:
    - current password was shared out-of-band
    - username is `demo`
- reviewer gets `429`
  - check:
    - recent request burst
  - action:
    - wait for retry window
- reviewer reports `/ready` is unhealthy
  - check:
    - Koyeb env vars
    - DB connectivity
- reviewer says the password stopped working after rotation
  - check:
    - Koyeb secret updated
    - GitHub Actions secret updated
    - reviewer refreshed local client/UI
- reviewer reports very slow first response
  - likely:
    - cold start
  - action:
    - retry with `--timeout 90`
- reviewer needs help tracing a specific call
  - ask for:
    - `X-Request-Id`

## Where To Inspect Logs

- hosted:
  - Koyeb service logs
  - search by:
    - `X-Request-Id`
    - `stream=query`
    - `stream=approval`
    - `stream=retrieval`
- local trace helpers:
  - `make inspect-logs`
  - `python scripts/inspect_logs.py --request-id <REQUEST_ID>`

## Cleanup After Live Approval Tests

- if a live smoke run created approval artifacts:

```bash
source .venv/bin/activate
set -a
source .env.local
set +a
python -m scripts.cleanup_demo_data --scope approvals --apply
```
