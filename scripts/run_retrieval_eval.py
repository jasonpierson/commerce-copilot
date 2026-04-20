#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.retrieval.evals.evaluator import EvalRunnerError, run_evaluation, write_report


def parse_args() -> argparse.Namespace:
    default_eval = ROOT / "app" / "retrieval" / "evals" / "retrieval_eval_set.jsonl"
    default_output = ROOT / "retrieval_eval_report.json"

    parser = argparse.ArgumentParser(description="Run retrieval-quality evaluation.")
    parser.add_argument("--mode", choices=["stub", "adapter"], default="stub")
    parser.add_argument("--eval-set", type=Path, default=default_eval)
    parser.add_argument("--output", type=Path, default=default_output)
    parser.add_argument("--top-k", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = run_evaluation(args.eval_set, mode=args.mode, top_k=args.top_k)
        write_report(report, args.output)
    except EvalRunnerError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except NotImplementedError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    summary = report["summary"]
    print(json.dumps(summary, indent=2))
    print(f"\nWrote report to: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())