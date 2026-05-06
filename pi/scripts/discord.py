"""Discord webhook notifier (stdlib only, failures only)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


def post_failure(text: str) -> None:
    """Send a single message to Discord. Silent on transport failure."""
    webhook = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook:
        return
    body = json.dumps({"content": text[:1900]}).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=10).read()
    except urllib.error.URLError:
        pass
    except Exception:  # noqa: BLE001 - notification must never escalate
        pass
