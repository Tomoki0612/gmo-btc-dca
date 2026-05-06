"""Display formatters (verbatim from settings-api Lambda)."""

from .constants import WEEKDAYS


def _fmt_schedule(freq, day):
    if not freq:
        return "—"
    if freq == "daily":
        return "毎日"
    if freq == "weekly":
        try:
            return f"毎週 {WEEKDAYS[int(day) - 1]}曜日"
        except (TypeError, ValueError, IndexError):
            return "毎週"
    if freq == "monthly":
        if day is None:
            return "毎月"
        return f"毎月 {int(day)}日"
    return freq


def _fmt_yen(n):
    try:
        return f"¥{int(n):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_time(h):
    if h is None:
        return "—"
    try:
        return f"{int(h):02d}:00"
    except (TypeError, ValueError):
        return "—"
