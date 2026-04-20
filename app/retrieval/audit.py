from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AuditSink:
    enabled: bool = True

    def log_event(self, **payload: Any) -> None:
        if not self.enabled:
            return
        print(payload)