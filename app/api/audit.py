from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


@dataclass(slots=True)
class ApiAuditSink:
    enabled: bool = True
    filename: str = "application_events.jsonl"
    output_path: Path | None = None

    def __post_init__(self) -> None:
        if self.output_path is None:
            artifacts_dir = Path(os.getenv("ARTIFACTS_DIR", "./artifacts")).resolve()
            self.output_path = artifacts_dir / self.filename
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, **payload: Any) -> None:
        if not self.enabled:
            return
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, default=_json_default) + "\n")
