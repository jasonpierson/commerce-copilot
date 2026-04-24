#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

import requests

from app.api.auth import build_demo_access_headers

ROOT_QUERY = "What is the return process for damaged products?"
INVENTORY_QUERY = "Check inventory for the Phantom X shoes."
INCIDENT_QUERY = "Summarize incident INC-1091 and tell me the likely customer impact."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test a hosted CommerceOpsCopilot demo.")
    parser.add_argument("--base-url", default=os.getenv("GCOP_API_BASE", "").strip())
    parser.add_argument("--password", default=os.getenv("DEMO_ACCESS_PASSWORD", "").strip())
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--skip-approval-flow", action="store_true")
    return parser.parse_args()


def build_headers(*, password: str, user_id: str, user_role: str) -> dict[str, str]:
    headers = {
        "X-User-Id": user_id,
        "X-User-Role": user_role,
    }
    return {**headers, **build_demo_access_headers(password)}


def ensure_ok(response: requests.Response, label: str) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        payload = {"raw_text": response.text[:500]}
    if response.status_code >= 400:
        raise RuntimeError(f"{label} failed with {response.status_code}: {payload}")
    return payload


def post_json(base_url: str, path: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
    response = requests.post(f"{base_url.rstrip('/')}{path}", json=payload, headers=headers, timeout=timeout)
    return ensure_ok(response, path)


def get_json(base_url: str, path: str, headers: dict[str, str], timeout: int) -> dict[str, Any]:
    response = requests.get(f"{base_url.rstrip('/')}{path}", headers=headers, timeout=timeout)
    return ensure_ok(response, path)


def main() -> int:
    args = parse_args()
    if not args.base_url:
        print("Missing base URL. Set GCOP_API_BASE or pass --base-url.", file=sys.stderr)
        return 1

    support_headers = build_headers(
        password=args.password,
        user_id="demo-support-001",
        user_role="support_analyst",
    )
    manager_headers = build_headers(
        password=args.password,
        user_id="demo-ops-manager-001",
        user_role="ops_manager",
    )
    engineering_headers = build_headers(
        password=args.password,
        user_id="demo-engineering-support-001",
        user_role="engineering_support",
    )

    checks: list[tuple[str, bool, str]] = []

    try:
        root = get_json(args.base_url, "/", headers={}, timeout=args.timeout)
        checks.append(("root", "/docs" in [item["href"] for item in root.get("next_steps", [])], "root landing"))

        health = get_json(args.base_url, "/health", headers={}, timeout=args.timeout)
        checks.append(("health", health.get("status") == "ok", f"status={health.get('status')}"))

        ready = get_json(args.base_url, "/ready", headers={}, timeout=args.timeout)
        checks.append(("ready", ready.get("status") == "ready", f"status={ready.get('status')}"))

        unauthorized = requests.post(
            f"{args.base_url.rstrip('/')}/api/v1/query",
            json={"message": ROOT_QUERY},
            timeout=args.timeout,
        )
        checks.append(("password_gate", unauthorized.status_code == 401, f"status={unauthorized.status_code}"))

        policy = post_json(
            args.base_url,
            "/api/v1/query",
            {"message": ROOT_QUERY},
            support_headers,
            args.timeout,
        )
        checks.append(("policy_query", policy.get("route_type") == "policy_qa", f"route={policy.get('route_type')}"))

        inventory = post_json(
            args.base_url,
            "/api/v1/query",
            {"message": INVENTORY_QUERY},
            support_headers,
            args.timeout,
        )
        checks.append((
            "inventory_query",
            inventory.get("route_type") == "structured_lookup",
            f"route={inventory.get('route_type')}",
        ))

        incident = post_json(
            args.base_url,
            "/api/v1/query",
            {"message": INCIDENT_QUERY},
            engineering_headers,
            args.timeout,
        )
        checks.append((
            "incident_query",
            incident.get("route_type") == "incident_summary",
            f"route={incident.get('route_type')}",
        ))

        if not args.skip_approval_flow:
            approval_request = post_json(
                args.base_url,
                "/api/v1/escalations",
                {
                    "incident_code": "INC-1091",
                    "escalation_reason": "Hosted smoke test escalation request.",
                    "proposed_priority": "critical",
                    "draft_summary": "Disposable hosted smoke-test approval request.",
                },
                support_headers,
                args.timeout,
            )
            approval_id = approval_request["data"]["approval"]["approval_id"]
            checks.append(("approval_create", True, f"approval_id={approval_id}"))

            approval_status = get_json(
                args.base_url,
                f"/api/v1/approvals/{approval_id}",
                manager_headers,
                args.timeout,
            )
            checks.append((
                "approval_status",
                approval_status["data"]["approval"]["status"] == "pending",
                f"status={approval_status['data']['approval']['status']}",
            ))

            approval_decision = post_json(
                args.base_url,
                f"/api/v1/approvals/{approval_id}/decision",
                {
                    "decision": "rejected",
                    "decision_notes": "Disposable hosted smoke test request rejected after verification.",
                },
                manager_headers,
                args.timeout,
            )
            checks.append((
                "approval_decision",
                approval_decision["data"]["approval"]["status"] == "rejected",
                f"status={approval_decision['data']['approval']['status']}",
            ))

    except Exception as exc:
        checks.append(("exception", False, str(exc)))

    print("Hosted demo smoke test results:")
    failures = 0
    for name, ok, detail in checks:
        marker = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"- {marker} {name}: {detail}")

    if failures:
        print(f"Smoke test failed with {failures} failing check(s).", file=sys.stderr)
        return 1

    print("- PASS summary: all hosted checks succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
