#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

from app.common.config import missing_required_runtime_env, validate_runtime_environment


def main() -> int:
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    try:
        validate_runtime_environment(app_env=app_env)
    except RuntimeError as exc:
        print(f"FAIL startup validation: {exc}", file=sys.stderr)
        return 1

    missing_ready = missing_required_runtime_env(app_env=app_env)
    print(f"PASS startup validation for APP_ENV={app_env}")
    if missing_ready:
        print("WARN readiness would still fail due to missing env:")
        for name in missing_ready:
            print(f"- {name}")
    else:
        print("PASS readiness env requirements satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
