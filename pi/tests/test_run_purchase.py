"""Schedule-gate and dup-guard tests for run_purchase.

We patch _fetch_btc_price and place_market_buy so no network is hit.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from pi.api.constants import JST


# A fixed JST instant: Tuesday 2026-05-05 09:00 JST.
# weekday()+1 == 2 (Tue), day == 5, hour == 9.
NOW = datetime(2026, 5, 5, 9, 0, 0, tzinfo=JST)


@pytest.fixture
def patched(monkeypatch, db_path):
    """Patch network + clock; configure baseline settings."""
    from pi.api import settings as settings_mod
    from pi.purchase import run_purchase

    monkeypatch.setattr(run_purchase, "_fetch_btc_price", lambda: 15_000_000.0)
    monkeypatch.setattr(run_purchase, "place_market_buy", lambda k, s, size: {"status": 0})

    class _DT(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    # run_purchase imports datetime from datetime module; patch the symbol it uses.
    monkeypatch.setattr(run_purchase, "datetime", _DT)
    # settings.put_purchase / already_purchased_today also use datetime.now(JST).
    monkeypatch.setattr(settings_mod, "datetime", _DT)
    return run_purchase


def _seed(db_path, **overrides):
    from pi.api.db import connect
    from pi.api.settings import upsert_settings

    base = {
        "amount": 1000,
        "frequency": "monthly",
        "scheduleDay": 5,
        "scheduleTime": 9,
        "apiKey": "k",
        "apiSecret": "s",
    }
    base.update(overrides)
    c = connect(db_path)
    try:
        upsert_settings(c, base)
    finally:
        c.close()


def _purchase_count(db_path):
    from pi.api.db import connect
    from pi.api.settings import list_history

    c = connect(db_path)
    try:
        return sum(1 for h in list_history(c) if h["type"] == "purchase")
    finally:
        c.close()


def test_unconfigured_skips_silently(patched, db_path):
    # No settings written -> no history, exit 0
    assert patched.main() == 0
    assert _purchase_count(db_path) == 0


def test_runs_on_matching_monthly(patched, db_path):
    _seed(db_path)
    assert patched.main() == 0
    assert _purchase_count(db_path) == 1


def test_skips_on_wrong_hour(patched, db_path):
    _seed(db_path, scheduleTime=10)
    assert patched.main() == 0
    assert _purchase_count(db_path) == 0


def test_skips_on_wrong_monthly_day(patched, db_path):
    _seed(db_path, scheduleDay=15)
    assert patched.main() == 0
    assert _purchase_count(db_path) == 0


def test_skips_on_wrong_weekly_day(patched, db_path):
    # NOW is Tuesday (weekday+1 == 2). Configure for Friday (5).
    _seed(db_path, frequency="weekly", scheduleDay=5)
    assert patched.main() == 0
    assert _purchase_count(db_path) == 0


def test_runs_on_matching_weekly(patched, db_path):
    _seed(db_path, frequency="weekly", scheduleDay=2)
    assert patched.main() == 0
    assert _purchase_count(db_path) == 1


def test_runs_daily_when_hour_matches(patched, db_path):
    _seed(db_path, frequency="daily", scheduleDay=None, scheduleTime=9)
    assert patched.main() == 0
    assert _purchase_count(db_path) == 1


def test_dup_guard_prevents_double_purchase(patched, db_path):
    _seed(db_path)
    assert patched.main() == 0
    assert patched.main() == 0  # second call same JST day
    assert _purchase_count(db_path) == 1


def test_failed_purchase_records_history_and_exits_1(patched, db_path, monkeypatch):
    _seed(db_path)

    def boom(*_, **__):
        raise RuntimeError("simulated GMO API outage")

    monkeypatch.setattr(patched, "place_market_buy", boom)
    assert patched.main() == 1
    # One failed-status row should exist; dup-guard ignores failed ones, so a
    # subsequent successful run on the same day is still allowed.
    from pi.api.db import connect
    from pi.api.settings import list_history

    c = connect(db_path)
    try:
        rows = [h for h in list_history(c) if h["type"] == "purchase"]
    finally:
        c.close()
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"


def test_dry_run_writes_ok_history_without_calling_order(patched, db_path, monkeypatch):
    _seed(db_path)
    called = []
    monkeypatch.setattr(patched, "place_market_buy", lambda *a, **k: called.append(a))
    monkeypatch.setenv("DRY_RUN", "true")
    assert patched.main() == 0
    assert called == []
    assert _purchase_count(db_path) == 1
