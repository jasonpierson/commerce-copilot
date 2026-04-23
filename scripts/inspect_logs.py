#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect JSONL audit logs in artifacts/.")
    parser.add_argument(
        "--file",
        choices=["query", "approval", "retrieval", "all"],
        default="all",
        help="Choose which log stream to inspect.",
    )
    parser.add_argument("--tail", type=int, default=20, help="Number of recent events to print.")
    parser.add_argument("--request-id", dest="request_id", help="Filter by request_id.")
    parser.add_argument("--approval-id", dest="approval_id", help="Filter by approval_id.")
    return parser.parse_args()


def resolve_log_paths(selection: str) -> list[Path]:
    artifacts_dir = Path(os.getenv("ARTIFACTS_DIR", "./artifacts")).resolve()
    mapping = {
        "query": artifacts_dir / "query_events.jsonl",
        "approval": artifacts_dir / "approval_events.jsonl",
        "retrieval": artifacts_dir / "retrieval_events.jsonl",
    }
    if selection == "all":
        return list(mapping.values())
    return [mapping[selection]]


def load_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                payload = {"raw_line": line}
            payload["_source_file"] = path.name
            events.append(payload)
    return events


def filter_events(
    events: list[dict[str, Any]],
    *,
    request_id: str | None,
    approval_id: str | None,
) -> list[dict[str, Any]]:
    filtered = events
    if request_id:
        filtered = [event for event in filtered if event.get("request_id") == request_id]
    if approval_id:
        filtered = [
            event
            for event in filtered
            if event.get("approval_id") == approval_id
            or event.get("payload", {}).get("approval_id") == approval_id
        ]
    return filtered


def event_sort_key(event: dict[str, Any]) -> tuple[str, str]:
    return (
        str(event.get("timestamp") or event.get("occurred_at") or event.get("requested_at") or ""),
        str(event.get("request_id") or event.get("audit_event_id") or ""),
    )


def print_event(event: dict[str, Any]) -> None:
    source = event.get("_source_file", "unknown")
    route = event.get("route_type", "-")
    request_id = event.get("request_id", "-")
    approval_id = event.get("approval_id") or event.get("payload", {}).get("approval_id") or "-"
    headline = event.get("message") or event.get("event_type") or event.get("tool_name") or "event"
    print(f"[{source}] route={route} request_id={request_id} approval_id={approval_id}")
    print(f"  headline: {headline}")
    print(json.dumps(event, indent=2, sort_keys=True))


def main() -> int:
    args = parse_args()
    events: list[dict[str, Any]] = []
    for path in resolve_log_paths(args.file):
        events.extend(load_events(path))

    filtered = filter_events(events, request_id=args.request_id, approval_id=args.approval_id)
    filtered.sort(key=event_sort_key)
    selected = filtered[-args.tail :] if args.tail > 0 else filtered

    if not selected:
        print("No matching events found.")
        return 0

    print(f"Showing {len(selected)} event(s).")
    for event in selected:
        print_event(event)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
