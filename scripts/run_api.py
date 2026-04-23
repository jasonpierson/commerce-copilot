#!/usr/bin/env python3
from __future__ import annotations

import os

import uvicorn


def main() -> None:
    app_host = os.getenv("APP_HOST", "127.0.0.1")
    app_port = int(os.getenv("APP_PORT", "8000"))
    app_env = os.getenv("APP_ENV", "development").strip().lower()
    uvicorn.run(
        "app.api.main:app",
        host=app_host,
        port=app_port,
        reload=app_env == "development",
    )


if __name__ == "__main__":
    main()
