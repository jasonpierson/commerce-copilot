from __future__ import annotations

import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Any


@dataclass
class AuditSink:
    enabled: bool = True
    output_path: Path | None = None

    def __post_init__(self) -> None:
        if self.output_path is None:
            artifacts_dir = Path(os.getenv("ARTIFACTS_DIR", "./artifacts")).resolve()
            self.output_path = artifacts_dir / "retrieval_events.jsonl"
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def log_event(self, **payload: Any) -> None:
        if not self.enabled:
            return
        with self.output_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
        print(payload)
