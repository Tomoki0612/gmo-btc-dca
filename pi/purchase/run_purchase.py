"""Hourly DCA purchase runner.

Invoked by btc-dca-purchase.timer every hour at :00. Decides whether to buy
based on the user's settings, runs the order, records history, and notifies
Discord on failure only.

Exit codes:
    0  - success, or correctly skipped (out-of-schedule, dup-guarded, unconfigured)
    1  - purchase attempted but failed (fires systemd Restart=on-failure)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

from pi.api.constants import JST
from pi.api.db import get_conn
from pi.api.gmo import _fetch_btc_price, place_market_buy
from pi.api.settings import already_purchased_today, get_settings, put_purchase
from pi.scripts.discord import post_failure


def _is_dry_run() -> bool:
    return os.environ.get("DRY_RUN", "").strip().lower() == "true"


def _should_run(settings: dict, now: datetime) -> tuple[bool, str]:
    """Return (run?, reason). The reason is for logging only."""
    schedule_time = settings.get("scheduleTime")
    if schedule_time is not None and now.hour != int(schedule_time):
        return False, f"out-of-hour: now={now.hour} cfg={schedule_time}"

    frequency = settings.get("frequency")
    schedule_day = settings.get("scheduleDay")

    if frequency == "weekly":
        # Python weekday: Mon=0..Sun=6 -> our scheduleDay convention: Mon=1..Sun=7
        if schedule_day and now.weekday() + 1 != int(schedule_day):
            return False, f"out-of-weekday: now={now.weekday() + 1} cfg={schedule_day}"
    elif frequency == "monthly":
        if schedule_day and now.day != int(schedule_day):
            return False, f"out-of-monthday: now={now.day} cfg={schedule_day}"
    # daily: hour gate above is sufficient

    return True, "match"


def main() -> int:
    dry_run = _is_dry_run()
    with get_conn() as conn:
        settings = get_settings(conn)
        api_key = settings.get("apiKey")
        api_secret = settings.get("apiSecret")
        amount = int(settings.get("amount") or 0)

        if not api_key or not api_secret or amount <= 0:
            print("settings incomplete; skipping (no history written)")
            return 0

        now = datetime.now(JST)
        run, reason = _should_run(settings, now)
        if not run:
            print(f"skip: {reason}")
            return 0

        if already_purchased_today(conn):
            print("skip: already purchased today (dup-guard)")
            return 0

        try:
            rate = _fetch_btc_price()
            size = round(amount / rate, 5)
            if dry_run:
                print(f"DRY_RUN: would buy size={size} BTC at rate={rate}")
                put_purchase(conn, status="ok", amount_jpy=amount, btc=size, rate=rate, reason="DRY_RUN")
                return 0

            place_market_buy(api_key, api_secret, size)
            put_purchase(conn, status="ok", amount_jpy=amount, btc=size, rate=rate)
            print(f"ok: bought size={size} BTC at rate={rate}")
            return 0
        except Exception as e:  # noqa: BLE001
            reason_text = str(e)[:200]
            print(f"failed: {reason_text}", file=sys.stderr)
            try:
                put_purchase(conn, status="failed", amount_jpy=amount, reason=reason_text)
            except Exception as ee:  # noqa: BLE001
                print(f"history write failed: {ee}", file=sys.stderr)
            post_failure(
                f"BTC積立失敗 {now.strftime('%Y-%m-%d %H:%M')} JST\n"
                f"金額: ¥{amount:,}\n"
                f"原因: {reason_text}"
            )
            return 1


if __name__ == "__main__":
    sys.exit(main())
