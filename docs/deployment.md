# Deployment Path

## Authoritative Target

- platform:
  - Koyeb
- hosted surface:
  - FastAPI API only
- local-only surface:
  - Streamlit demo UI
- source of truth:
  - this repo's `Dockerfile`

## Goal

- keep setup minimal
- make one deployment path feel real
- avoid pretending this repo ships full production infra
- give reviewers one clear way to run the API fast

## Prerequisites

- Python `3.11+`
- local `.env.local` with:
  - `OPENAI_API_KEY`
  - `SUPABASE_DB_URL`
  - `DEMO_ACCESS_PASSWORD`
- backend-visible application schema:
  - `DB_APP_SCHEMA=app_private` by default
- seeded operational data for the structured demo paths

## Fastest Local Flow

```bash
make install
make check-db-schema
make seed
make run-api
```

In a second shell:

```bash
make demo
```

## Useful Make Targets

- `make test`
- `make eval`
- `make smoke`
- `make inspect-logs`
- `make clean-approvals`
- `make clean-full`

## Production-Lite Runtime Env

- `APP_ENV`
  - `development` enables reload in `scripts/run_api.py`
  - `production` disables reload
- `APP_HOST`
  - defaults to `127.0.0.1`
- `APP_PORT`
  - defaults to `8000`
- `DEMO_ACCESS_PASSWORD`
  - when set, all non-`/health` API routes require the demo password

## Koyeb Path

- deploy from GitHub using the repo `Dockerfile`
- reference guide:
  - Koyeb FastAPI deploy docs: https://www.koyeb.com/docs/deploy/fastapi
- keep the API as the only hosted component
- set the service env vars:
  - `OPENAI_API_KEY`
  - `SUPABASE_DB_URL`
  - `DEMO_ACCESS_PASSWORD`
  - `DB_APP_SCHEMA=app_private`
  - `APP_ENV=production`
  - `APP_HOST=0.0.0.0`
  - `APP_PORT=8000`
- reviewer experience:
  - use the hosted `/docs` with Basic auth
  - or point local Streamlit at the hosted API with `GCOP_API_BASE`

## Why Streamlit Stays Local

- it is a reviewer convenience layer, not the product surface
- the API already provides the stronger demo:
  - `/docs`
  - curl
  - `scripts/demo_queries.py`
- keeping Streamlit local reduces public attack surface and hosting complexity

## Notes

- retrieval and structured lookups both depend on the external Postgres/Supabase database
- application tables are expected to live in `app_private`, not `public`
- this repo now has one recommended hosted path, but it is still a production-lite deployment
- for public exposure hardening, use `SECURITY.md`
