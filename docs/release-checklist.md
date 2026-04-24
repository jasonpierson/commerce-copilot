# Hosted Demo Release Checklist

## Before Deploy

- confirm required env vars exist:
  - `OPENAI_API_KEY`
  - `SUPABASE_DB_URL`
  - `DEMO_ACCESS_PASSWORD`
  - `DB_APP_SCHEMA=app_private`
- confirm local tests pass:
  - `make test-api`
- confirm seed/demo data is in a good state:
  - `make check-db-schema`
  - `make seed` if needed

## Deploy

- push the target branch/commit to GitHub
- deploy/update the Koyeb service using:
  - `koyeb.yaml`
  - `Dockerfile`
- verify Koyeb health check target:
  - `/ready`

## After Deploy

- run remote smoke:
  - `make smoke-remote-live`
- verify:
  - `/health`
  - `/ready`
  - password gate rejects missing auth
  - `/docs` loads with the shared password
  - one approval flow works end to end

## Logs / Debugging

- inspect platform logs for:
  - `stream=query`
  - `stream=retrieval`
  - `stream=approval`
- if a smoke test fails, trace by `request_id`
- for local reproduction:
  - `make inspect-logs`

## Cleanup

- remove disposable approval smoke-test artifacts if you created them:
  - `make clean-approvals`

## Rollback

- redeploy the previous known-good Git commit
- rerun:
  - `make smoke-remote`

## Hosted Demo URL

- current hosted demo URL:
  - `https://harsh-juieta-jasons-org-14a2695f.koyeb.app/`
