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
    return psycopg.connect(dsn or require_dsn(), row_factory=dict_row)
