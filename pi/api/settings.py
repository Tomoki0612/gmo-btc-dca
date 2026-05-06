"""Settings + history persistence (SQLite)."""

from __future__ import annotations

import sqlite3
import time
import uuid
from datetime import datetime
from typing import Any

from .constants import JST, USER_ID
from .formatters import _fmt_schedule, _fmt_time, _fmt_yen


# ---------- key translation ----------

_SETTINGS_DB_TO_API = {
    "amount": "amount",
    "frequency": "frequency",
    "schedule_day": "scheduleDay",
    "schedule_time": "scheduleTime",
    "api_key": "apiKey",
    "api_secret": "apiSecret",
    "updated_at": "updatedAt",
}

_SETTINGS_API_TO_DB = {v: k for k, v in _SETTINGS_DB_TO_API.items()}

_API_FIELDS = ["amount", "frequency", "scheduleDay", "scheduleTime", "apiKey", "apiSecret"]


def _row_to_settings(row: sqlite3.Row | None) -> dict[str, Any]:
    if row is None:
        return {}
    out: dict[str, Any] = {"userId": row["user_id"]}
    for db_key, api_key in _SETTINGS_DB_TO_API.items():
        val = row[db_key]
        if val is not None:
            out[api_key] = val
    return out


# ---------- settings ----------

def get_settings(conn: sqlite3.Connection) -> dict[str, Any]:
    cur = conn.execute("SELECT * FROM settings WHERE user_id = ?", (USER_ID,))
    return _row_to_settings(cur.fetchone())


def upsert_settings(conn: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    """Apply non-empty fields from `payload` and record diffs to history.

    Returns the merged settings dict (post-write, in API key shape).
    """
    existing = get_settings(conn)
    merged = dict(existing)
    for key in _API_FIELDS:
        val = payload.get(key)
        if val is not None and val != "":
            merged[key] = val
    merged["updatedAt"] = datetime.now(JST).isoformat(timespec="seconds")

    # Build column list, USER_ID always present.
    cols = ["user_id"]
    vals: list[Any] = [USER_ID]
    for api_key in _API_FIELDS + ["updatedAt"]:
        db_key = _SETTINGS_API_TO_DB[api_key]
        cols.append(db_key)
        vals.append(merged.get(api_key))
    placeholders = ",".join("?" for _ in cols)
    update_clause = ",".join(f"{c}=excluded.{c}" for c in cols if c != "user_id")
    sql = (
        f"INSERT INTO settings ({','.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT(user_id) DO UPDATE SET {update_clause}"
    )
    conn.execute(sql, vals)

    try:
        _diff_and_record(conn, existing, merged)
    except Exception as e:  # noqa: BLE001
        print(f"diff record failed: {e}")

    return merged


def _diff_and_record(conn: sqlite3.Connection, old: dict[str, Any], new: dict[str, Any]) -> None:
    if int(old.get("amount") or 0) != int(new.get("amount") or 0):
        _put_change(conn, "amount", _fmt_yen(old.get("amount")), _fmt_yen(new.get("amount")))

    old_freq = old.get("frequency")
    new_freq = new.get("frequency")
    old_day = old.get("scheduleDay")
    new_day = new.get("scheduleDay")
    if old_freq != new_freq or (new_freq != "daily" and old_day != new_day):
        _put_change(
            conn,
            "schedule",
            _fmt_schedule(old_freq, old_day),
            _fmt_schedule(new_freq, new_day),
        )

    if (old.get("scheduleTime") if old.get("scheduleTime") is not None else None) != (
        new.get("scheduleTime") if new.get("scheduleTime") is not None else None
    ):
        _put_change(
            conn,
            "time",
            _fmt_time(old.get("scheduleTime")),
            _fmt_time(new.get("scheduleTime")),
        )

    old_api = bool(old.get("apiKey") and old.get("apiSecret"))
    new_api = bool(new.get("apiKey") and new.get("apiSecret"))
    if old_api != new_api:
        _put_change(
            conn,
            "api",
            "未設定" if not old_api else "設定済み",
            "設定済み" if new_api else "未設定",
        )


# ---------- history ----------

def _now_sk(prefix: str) -> str:
    ts = int(time.time() * 1000)
    return f"{ts:013d}#{prefix}#{uuid.uuid4().hex[:6]}"


def _put_change(conn: sqlite3.Connection, field: str, before: str, after: str) -> None:
    sk = _now_sk("change")
    conn.execute(
        "INSERT INTO history (id, user_id, type, at, field, before_val, after_val) "
        "VALUES (?, ?, 'change', ?, ?, ?, ?)",
        (sk, USER_ID, datetime.now(JST).isoformat(timespec="seconds"), field, before, after),
    )


def put_purchase(
    conn: sqlite3.Connection,
    status: str,
    amount_jpy: int | None,
    btc: float | None = None,
    rate: float | None = None,
    reason: str | None = None,
) -> None:
    sk = _now_sk("purchase")
    conn.execute(
        "INSERT INTO history (id, user_id, type, at, status, amount, btc, rate, reason) "
        "VALUES (?, ?, 'purchase', ?, ?, ?, ?, ?, ?)",
        (
            sk,
            USER_ID,
            datetime.now(JST).isoformat(timespec="seconds"),
            status,
            int(amount_jpy) if amount_jpy is not None else None,
            float(round(btc, 8)) if btc is not None else None,
            float(round(rate, 2)) if rate is not None else None,
            (str(reason)[:200] if reason else None),
        ),
    )


def list_history(conn: sqlite3.Connection, limit: int = 200) -> list[dict[str, Any]]:
    cur = conn.execute(
        "SELECT * FROM history WHERE user_id = ? ORDER BY at DESC LIMIT ?",
        (USER_ID, limit),
    )
    items: list[dict[str, Any]] = []
    for row in cur.fetchall():
        t = row["type"]
        item: dict[str, Any] = {
            "id": row["id"],
            "type": t,
            "at": row["at"],
        }
        if t == "purchase":
            item.update(
                {
                    "status": row["status"],
                    "amount": row["amount"],
                    "btc": row["btc"],
                    "rate": row["rate"],
                    "reason": row["reason"],
                }
            )
        elif t == "change":
            item.update(
                {
                    "field": row["field"],
                    "before": row["before_val"],
                    "after": row["after_val"],
                }
            )
        items.append(item)
    return items


def already_purchased_today(conn: sqlite3.Connection) -> bool:
    """Return True if a successful purchase already exists for the current JST day."""
    today = datetime.now(JST).strftime("%Y-%m-%d")
    cur = conn.execute(
        "SELECT 1 FROM history "
        "WHERE user_id = ? AND type = 'purchase' AND status = 'ok' AND at >= ? "
        "LIMIT 1",
        (USER_ID, today),
    )
    return cur.fetchone() is not None
