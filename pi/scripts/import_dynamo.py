"""One-shot import of DynamoDB exports into the Pi SQLite DB.

Run on a workstation that has AWS CLI access:

    aws dynamodb scan --table-name btc-dca-settings --output json > settings.json
    aws dynamodb scan --table-name btc-dca-history  --output json > history.json
    scp settings.json history.json pi:/tmp/
    ssh pi 'cd /opt/btc-dca && .venv/bin/python -m pi.scripts.import_dynamo \
        --settings /tmp/settings.json --history /tmp/history.json'

The script accepts either raw `aws dynamodb scan` output (Items[] with type
markers like {"S":"foo"}) or a pre-flattened JSON list of dicts.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from pi.api.constants import USER_ID
from pi.api.db import connect


def _unwrap(v: Any) -> Any:
    """Unwrap a DynamoDB-typed value if needed."""
    if isinstance(v, dict) and len(v) == 1:
        (tag, val), = v.items()
        if tag == "S":
            return val
        if tag == "N":
            try:
                if "." in val:
                    return float(val)
                return int(val)
            except ValueError:
                return val
        if tag == "BOOL":
            return bool(val)
        if tag == "NULL":
            return None
        if tag == "L":
            return [_unwrap(i) for i in val]
        if tag == "M":
            return {k: _unwrap(i) for k, i in val.items()}
    return v


def _load_items(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    items = data.get("Items", data) if isinstance(data, dict) else data
    return [{k: _unwrap(v) for k, v in row.items()} for row in items]


def _import_settings(conn, items: list[dict[str, Any]]) -> int:
    n = 0
    for it in items:
        if it.get("userId") != USER_ID:
            continue
        conn.execute(
            "INSERT INTO settings (user_id, amount, frequency, schedule_day, schedule_time, "
            "api_key, api_secret, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "amount=excluded.amount, frequency=excluded.frequency, "
            "schedule_day=excluded.schedule_day, schedule_time=excluded.schedule_time, "
            "api_key=excluded.api_key, api_secret=excluded.api_secret, "
            "updated_at=excluded.updated_at",
            (
                USER_ID,
                int(it["amount"]) if it.get("amount") is not None else None,
                it.get("frequency"),
                int(it["scheduleDay"]) if it.get("scheduleDay") is not None else None,
                int(it["scheduleTime"]) if it.get("scheduleTime") is not None else None,
                it.get("apiKey"),
                it.get("apiSecret"),
                it.get("updatedAt"),
            ),
        )
        n += 1
    return n


def _import_history(conn, items: list[dict[str, Any]]) -> int:
    n = 0
    for it in items:
        if it.get("userId") != USER_ID:
            continue
        row_id = it.get("id") or it.get("sk")
        if not row_id:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO history "
            "(id, user_id, type, at, status, amount, btc, rate, reason, field, before_val, after_val) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                row_id,
                USER_ID,
                it.get("type"),
                it.get("at"),
                it.get("status"),
                int(it["amount"]) if it.get("amount") is not None else None,
                float(it["btc"]) if it.get("btc") is not None else None,
                float(it["rate"]) if it.get("rate") is not None else None,
                it.get("reason"),
                it.get("field"),
                it.get("before"),
                it.get("after"),
            ),
        )
        n += 1
    return n


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--settings", required=False)
    parser.add_argument("--history", required=False)
    parser.add_argument("--db", required=False, help="override DB path")
    args = parser.parse_args(argv[1:])

    conn = connect(args.db)
    try:
        if args.settings:
            n = _import_settings(conn, _load_items(args.settings))
            print(f"settings: imported {n} row(s)")
        if args.history:
            n = _import_history(conn, _load_items(args.history))
            print(f"history: imported {n} row(s)")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
