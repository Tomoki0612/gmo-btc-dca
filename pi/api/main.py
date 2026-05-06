"""FastAPI app exposing the same JSON shape as the AWS settings-api Lambda."""

from __future__ import annotations

import urllib.error
from datetime import datetime
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .db import get_conn
from .gmo import _fetch_assets, _fetch_btc_price
from .settings import get_settings, list_history, upsert_settings

app = FastAPI(title="btc-dca-api", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/api/settings")
def settings_get() -> dict[str, Any]:
    with get_conn() as conn:
        return get_settings(conn)


@app.post("/api/settings")
async def settings_post(request: Request) -> dict[str, str]:
    body = await request.json()
    with get_conn() as conn:
        upsert_settings(conn, body or {})
    return {"message": "saved"}


@app.get("/api/balance")
def balance() -> JSONResponse:
    with get_conn() as conn:
        s = get_settings(conn)
    api_key = s.get("apiKey")
    api_secret = s.get("apiSecret")
    if not api_key or not api_secret:
        return JSONResponse({"configured": False})

    try:
        assets = _fetch_assets(api_key, api_secret)
        rate = _fetch_btc_price()
    except urllib.error.HTTPError as e:
        return JSONResponse(
            {"configured": True, "message": f"GMOコインAPIエラー ({e.code})"},
            status_code=502,
        )
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"configured": True, "message": str(e)}, status_code=502)

    jpy = 0.0
    btc = 0.0
    for a in assets:
        sym = a.get("symbol")
        try:
            amt = float(a.get("amount", "0"))
        except (TypeError, ValueError):
            amt = 0.0
        if sym == "JPY":
            jpy = amt
        elif sym == "BTC":
            btc = amt

    return JSONResponse(
        {
            "configured": True,
            "jpy": jpy,
            "btc": btc,
            "btcJpyRate": rate,
            "updatedAt": datetime.utcnow().isoformat() + "Z",
        }
    )


@app.get("/api/history")
def history() -> dict[str, Any]:
    with get_conn() as conn:
        items = list_history(conn, limit=200)
    return {"items": items}
