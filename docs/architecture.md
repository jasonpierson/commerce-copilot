# Architecture Notes

## System Shape

```text
User / Support Agent
        |
        v
  /api/v1/query  ----------------------------+
        |                                    |
        | classify route                     |
        v                                    v
  Retrieval-backed paths              Structured data paths
  - policy_qa                         - inventory
  - incident_summary                  - incidents
  - escalation_guidance               - approvals
        |                                    |
        v                                    v
  Postgres vector corpus               Postgres operational tables
  + OpenAI embeddings                  + seeded demo domain data
        \                                    /
         \                                  /
          +----------- composed response ---+
```

## Main Flow

- `query_router.py`
  - receives the request
  - resolves mock principal headers
  - generates a request ID
- `query_service.py`
  - classifies the route
  - extracts IDs / filters
  - calls retrieval and/or structured services
  - builds the final response payload
- service layer
  - `incident_service.py`
  - `inventory_service.py`
  - `approval_service.py`
- audit/logging
  - retrieval traces -> `artifacts/retrieval_events.jsonl`
  - query traces -> `artifacts/query_events.jsonl`
  - approval traces -> `artifacts/approval_events.jsonl`

## Governance Boundary

- incident escalations are approval-gated
- approval create / status / decision / audit are explicit API paths
- mock auth headers define the acting principal:
  - `X-User-Id`
  - `X-User-Role`
- approval decisions are limited to:
  - `ops_manager`
  - `admin`

## Why This Matters

- retrieval shows grounded policy/runbook support
- structured services show operational realism
- approval workflows show governed action, not just chatbot output
- persistent request tracing makes the system inspectable after the demo ends
