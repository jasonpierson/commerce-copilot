#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

import uvicorn

from app.common.config import validate_runtime_environment


def main() -> None:
    app_host = os.getenv("APP_HOST", "127.0.0.1")
    app_port = int(os.getenv("PORT", os.getenv("APP_PORT", "8000")))
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    if app_env == "production":
        try:
            validate_runtime_environment(app_env=app_env)
        except RuntimeError as exc:
            print(f"Startup validation failed: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
    uvicorn.run(
        "app.api.main:app",
        host=app_host,
        port=app_port,
        reload=app_env == "development",
    )


if __name__ == "__main__":
    main()
