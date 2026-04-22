#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient

from app.api.main import app


def _print_step(title: str, payload: dict) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, indent=2))


def _post(client: TestClient, path: str, payload: dict) -> dict:
    response = client.post(path, json=payload)
    response.raise_for_status()
    return response.json()


def _get(client: TestClient, path: str) -> dict:
    response = client.get(path)
    response.raise_for_status()
    return response.json()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the golden-path CommerceOpsCopilot demo.")
    parser.add_argument(
        "--keep-approvals",
        action="store_true",
        help="Leave the disposable approval artifacts in place after the demo.",
    )
    return parser.parse_args()


def cleanup_approvals() -> None:
    subprocess.run(
        [sys.executable, "-m", "scripts.cleanup_demo_data", "--scope", "approvals", "--apply"],
        check=True,
    )


def main() -> int:
    args = parse_args()
    client = TestClient(app)

    policy = _post(
        client,
        "/api/v1/query",
        {
            "message": "What is the return process for damaged products?",
            "user_role": "support_analyst",
        },
    )
    _print_step("Policy Question", policy)

    inventory = _post(
        client,
        "/api/v1/query",
        {
            "message": "Check inventory for the Phantom X shoes.",
            "user_role": "support_analyst",
        },
    )
    _print_step("Inventory Lookup", inventory)

    incident = _post(
        client,
        "/api/v1/query",
        {
            "message": "Summarize incident INC-1091 and tell me the likely customer impact.",
            "user_role": "engineering_support",
        },
    )
    _print_step("Incident Summary", incident)

    approval_request = _post(
        client,
        "/api/v1/escalations",
        {
            "incident_code": "INC-1091",
            "requested_by_user_id": "demo-support-001",
            "requested_by_role": "support_analyst",
            "escalation_reason": "Golden-path demo escalation request.",
            "proposed_priority": "critical",
            "draft_summary": "Escalate due to sustained checkout impact.",
        },
    )
    _print_step("Create Approval", approval_request)
    approval_id = approval_request["data"]["approval"]["approval_id"]

    approval_status = _get(client, f"/api/v1/approvals/{approval_id}")
    _print_step("Approval Status", approval_status)

    approval_decision = _post(
        client,
        f"/api/v1/approvals/{approval_id}/decision",
        {
            "decision": "approved",
            "decision_notes": "Approved during scripted demo.",
            "decider_user_id": "demo-ops-manager-001",
            "decider_role": "ops_manager",
        },
    )
    _print_step("Approval Decision", approval_decision)

    approval_audit = _get(client, f"/api/v1/approvals/{approval_id}/audit")
    _print_step("Approval Audit", approval_audit)

    if not args.keep_approvals:
        cleanup_approvals()
        print("\n=== Cleanup ===")
        print("Removed disposable approval workflow artifacts.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
