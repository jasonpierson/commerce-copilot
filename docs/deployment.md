# Local Run Path

## Goal

- keep setup minimal
- avoid pretending this repo ships full production infra
- give reviewers one clear way to get the API running fast

## Prerequisites

- Python `3.11+`
- local `.env.local` with:
  - `OPENAI_API_KEY`
  - `SUPABASE_DB_URL`
- seeded operational data for the structured demo paths

## Fastest Local Flow

```bash
make install
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
- `make clean-approvals`
- `make clean-full`

## Notes

- retrieval and structured lookups both depend on the external Postgres/Supabase database
- this repo currently provides a developer-ops starter path, not a production deployment package
- for public exposure hardening, use `SECURITY.md`
