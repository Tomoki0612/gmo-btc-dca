"""GMO Coin API helpers (stdlib-only, ported verbatim from settings-api Lambda)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request

from .constants import GMO_PRIVATE, GMO_PUBLIC


def _http_get_json(url, headers=None, timeout=10):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def _sign(secret, timestamp, method, path, body=""):
    text = f"{timestamp}{method}{path}{body}"
    return hmac.new(
        secret.encode("ascii"), text.encode("ascii"), hashlib.sha256
    ).hexdigest()


def _fetch_assets(api_key, api_secret):
    timestamp = f"{int(time.time() * 1000)}"
    path = "/v1/account/assets"
    sign = _sign(api_secret, timestamp, "GET", path)
    headers = {
        "API-KEY": api_key,
        "API-TIMESTAMP": timestamp,
        "API-SIGN": sign,
    }
    data = _http_get_json(GMO_PRIVATE + path, headers=headers)
    if data.get("status") != 0:
        raise RuntimeError(f"GMO assets API error: {data.get('messages')}")
    return data.get("data", []) or []


def _fetch_btc_price():
    data = _http_get_json(f"{GMO_PUBLIC}/v1/ticker?symbol=BTC")
    if data.get("status") != 0 or not data.get("data"):
        raise RuntimeError("BTC価格の取得に失敗しました")
    return float(data["data"][0]["last"])


def place_market_buy(api_key, api_secret, size_btc):
    """Issue a BTC spot market buy. Returns the parsed JSON response.

    `size_btc` is a float; caller is responsible for rounding to 5 decimals.
    Raises on transport errors or non-zero GMO status.
    """
    timestamp = f"{int(time.time() * 1000)}"
    path = "/v1/order"
    body = json.dumps(
        {
            "symbol": "BTC",
            "side": "BUY",
            "executionType": "MARKET",
            "size": str(size_btc),
        }
    )
    sign = _sign(api_secret, timestamp, "POST", path, body)
    headers = {
        "API-KEY": api_key,
        "API-TIMESTAMP": timestamp,
        "API-SIGN": sign,
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(
        GMO_PRIVATE + path,
        data=body.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        data = json.loads(res.read().decode("utf-8"))
    if data.get("status") != 0:
        raise RuntimeError(f"GMO order error: {data.get('messages')}")
    return data
