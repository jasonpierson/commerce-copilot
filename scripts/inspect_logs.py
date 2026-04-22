#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

ARTIFACTS_DIR = Path(__file__).resolve().parent.parent / "artifacts"
FILES = [
    ARTIFACTS_DIR / "query_events.jsonl",
    ARTIFACTS_DIR / "retrieval_events.jsonl",
    ARTIFACTS_DIR / "approval_events.jsonl",
]


def load_events() -> list[Dict[str, Any]]:
    events: list[Dict[str, Any]] = []
    for file in FILES:
        if not file.exists():
            continue
        with file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except Exception:
                    continue
    # default newest last
    return events


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect JSONL artifacts for recent request traces.")
    parser.add_argument("--request-id", dest="request_id", help="Filter by request_id", default=None)
    parser.add_argument("--route-type", dest="route_type", help="Filter by route_type", default=None)
    parser.add_argument("--approval-id", dest="approval_id", help="Filter by approval_id (or in list)", default=None)
    parser.add_argument("--tail", dest="tail", help="Show last N events (default 50)", type=int, default=50)

    args = parser.parse_args()

    events = load_events()
    if args.request_id:
        events = [e for e in events if e.get("request_id") == args.request_id]
    if args.route_type:
        events = [e for e in events if e.get("route_type") == args.route_type]
    if args.approval_id:
        events = [
            e for e in events
            if e.get("approval_id") == args.approval_id or args.approval_id in (e.get("approval_ids") or [])
        ]

    tail_n = max(args.tail or 0, 0)
    if tail_n:
        events = events[-tail_n:]

    for e in events:
        print(json.dumps(e, ensure_ascii=False))


if __name__ == "__main__":
    main()
