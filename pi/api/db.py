"""SQLite connection helpers."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager

DEFAULT_DB_PATH = "/var/lib/btc-dca/dca.sqlite"


def db_path() -> str:
    return os.environ.get("BTC_DCA_DB", DEFAULT_DB_PATH)


def connect(path: str | None = None) -> sqlite3.Connection:
    """Open a connection with sane defaults (WAL, FK, dict rows)."""
    conn = sqlite3.connect(path or db_path(), timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_conn(path: str | None = None):
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()
