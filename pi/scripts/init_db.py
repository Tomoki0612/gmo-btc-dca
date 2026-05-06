"""Initialise the SQLite database (idempotent).

Usage:
    python -m pi.scripts.init_db [path]

If `path` is omitted, uses BTC_DCA_DB env var or DEFAULT_DB_PATH.
"""

from __future__ import annotations

import os
import pathlib
import sys

from pi.api.db import connect, db_path


SCHEMA_PATH = pathlib.Path(__file__).resolve().parent.parent / "api" / "schema.sql"


def init(path: str | None = None) -> str:
    target = path or db_path()
    parent = pathlib.Path(target).parent
    parent.mkdir(parents=True, exist_ok=True)

    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = connect(target)
    try:
        conn.executescript(schema)
    finally:
        conn.close()

    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return target


def main(argv: list[str]) -> int:
    path = argv[1] if len(argv) > 1 else None
    out = init(path)
    print(f"initialised: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
