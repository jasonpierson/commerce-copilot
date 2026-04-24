from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _normalize_event(stream: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "stream": stream,
        **payload,
    }


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
        event = _normalize_event(self.filename.replace("_events.jsonl", ""), payload)
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, default=_json_default) + "\n")
        print(json.dumps(event, default=_json_default), flush=True)
