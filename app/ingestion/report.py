from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .models import IngestionReport



def write_ingestion_report(report: IngestionReport, output_path: Path) -> None:
    report.finished_at = report.finished_at or IngestionReport.utc_now_iso()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "started_at": report.started_at,
        "finished_at": report.finished_at,
        "documents_succeeded": len(report.successes),
        "documents_failed": len(report.failures),
        "successes": [asdict(item) for item in report.successes],
        "failures": [asdict(item) for item in report.failures],
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
