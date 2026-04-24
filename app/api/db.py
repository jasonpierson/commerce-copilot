from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row


def require_dsn() -> str:
    dsn = os.getenv("SUPABASE_DB_URL")
    if not dsn:
        raise RuntimeError("SUPABASE_DB_URL is required for structured data access")
    return dsn


def connect(dsn: str | None = None):
    return psycopg.connect(dsn or require_dsn(), row_factory=dict_row, connect_timeout=5)


def check_connectivity(dsn: str | None = None) -> tuple[bool, str | None]:
    try:
        with connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True, None
    except Exception as exc:
        return False, type(exc).__name__
