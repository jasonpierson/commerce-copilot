# API Review Assets

## What This Folder Gives Reviewers

- a terminal-first review path
- a machine-readable review asset without relying on Swagger UI
- placeholder-safe examples that never commit secrets

## Included

- `curl-examples.md`
  - copy-paste hosted review commands
- `postman_collection.json`
  - importable collection for the hosted demo review path

## Required Variables

- `HOSTED_URL`
- `DEMO_PASSWORD`
- `APPROVAL_ID`

## Main Flows Covered

- policy query
- inventory lookup
- incident summary
- escalation creation
- approval status
- approval decision
