#!/usr/bin/env python3
from __future__ import annotations

from app.api.db import connect, require_dsn
from app.common.config import DB_APP_SCHEMA


CHECKS = (
    "documents",
    "document_chunks",
    "approvals",
)


def main() -> None:
    require_dsn()
    with connect() as conn:
        with conn.cursor() as cur:
            print(f"Checking backend access to schema: {DB_APP_SCHEMA}")
            for table_name in CHECKS:
                cur.execute(f"select count(*) from {DB_APP_SCHEMA}.{table_name}")
                count = cur.fetchone()["count"]
                print(f"- {DB_APP_SCHEMA}.{table_name}: {count} row(s)")


if __name__ == "__main__":
    main()
