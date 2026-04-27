# Hosted Demo Curl Examples

## Setup

```bash
export HOSTED_URL="<HOSTED_URL>"
export DEMO_PASSWORD="<DEMO_PASSWORD>"
```

## Version

```bash
curl -u "demo:${DEMO_PASSWORD}" \
  "${HOSTED_URL}/version"
```

## Policy Query

```bash
curl -u "demo:${DEMO_PASSWORD}" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: demo-support-001" \
  -H "X-User-Role: support_analyst" \
  -d '{"message":"What is the return process for damaged products?"}' \
  "${HOSTED_URL}/api/v1/query"
```

## Inventory Lookup

```bash
curl -u "demo:${DEMO_PASSWORD}" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: demo-support-001" \
  -H "X-User-Role: support_analyst" \
  -d '{"message":"Check inventory for the Phantom X shoes."}' \
  "${HOSTED_URL}/api/v1/query"
```

## Incident Summary

```bash
curl -u "demo:${DEMO_PASSWORD}" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: demo-engineering-support-001" \
  -H "X-User-Role: engineering_support" \
  -d '{"message":"Summarize incident INC-1091 and tell me the likely customer impact."}' \
  "${HOSTED_URL}/api/v1/query"
```

## Escalation Create

```bash
curl -u "demo:${DEMO_PASSWORD}" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: demo-support-001" \
  -H "X-User-Role: support_analyst" \
  -d '{"incident_code":"INC-1091","escalation_reason":"Reviewer demo escalation.","proposed_priority":"critical","draft_summary":"Disposable reviewer approval request."}' \
  "${HOSTED_URL}/api/v1/escalations"
```

## Approval Status

```bash
curl -u "demo:${DEMO_PASSWORD}" \
  -H "X-User-Id: demo-ops-manager-001" \
  -H "X-User-Role: ops_manager" \
  "${HOSTED_URL}/api/v1/approvals/<APPROVAL_ID>"
```

## Approval Decision

```bash
curl -u "demo:${DEMO_PASSWORD}" \
  -H "Content-Type: application/json" \
  -H "X-User-Id: demo-ops-manager-001" \
  -H "X-User-Role: ops_manager" \
  -d '{"decision":"rejected","decision_notes":"Disposable reviewer approval request rejected after validation."}' \
  "${HOSTED_URL}/api/v1/approvals/<APPROVAL_ID>/decision"
```

## Trace Tip

- capture:
  - `X-Request-Id`
- use it to correlate:
  - hosted logs
  - `scripts/inspect_logs.py`
