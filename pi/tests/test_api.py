"""End-to-end API tests via fastapi.testclient.

The /api/balance endpoint reaches GMO Coin in real life; here we monkeypatch the
fetch helpers so we can assert the JSON shape the frontend depends on.
"""

from fastapi.testclient import TestClient


def _client(db_path):
    from pi.api.main import app

    return TestClient(app)


def test_get_settings_empty(db_path):
    c = _client(db_path)
    r = c.get("/api/settings")
    assert r.status_code == 200
    assert r.json() == {}


def test_post_then_get_settings(db_path):
    c = _client(db_path)
    payload = {
        "amount": 3000,
        "frequency": "weekly",
        "scheduleDay": 2,
        "scheduleTime": 9,
        "apiKey": "k",
        "apiSecret": "s",
    }
    r = c.post("/api/settings", json=payload)
    assert r.status_code == 200
    assert r.json() == {"message": "saved"}

    r = c.get("/api/settings")
    body = r.json()
    for k, v in payload.items():
        assert body[k] == v


def test_history_shape(db_path):
    c = _client(db_path)
    c.post("/api/settings", json={"amount": 1000, "frequency": "daily", "scheduleTime": 9})
    r = c.get("/api/history")
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    for item in body["items"]:
        assert {"id", "type", "at"}.issubset(item.keys())
        if item["type"] == "change":
            assert {"field", "before", "after"}.issubset(item.keys())


def test_balance_unconfigured(db_path):
    c = _client(db_path)
    r = c.get("/api/balance")
    assert r.status_code == 200
    assert r.json() == {"configured": False}


def test_balance_configured(db_path, monkeypatch):
    from pi.api import main

    monkeypatch.setattr(
        main,
        "_fetch_assets",
        lambda k, s: [{"symbol": "JPY", "amount": "10000"}, {"symbol": "BTC", "amount": "0.005"}],
    )
    monkeypatch.setattr(main, "_fetch_btc_price", lambda: 15_000_000.0)

    c = _client(db_path)
    c.post("/api/settings", json={"apiKey": "k", "apiSecret": "s"})
    r = c.get("/api/balance")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["jpy"] == 10000.0
    assert body["btc"] == 0.005
    assert body["btcJpyRate"] == 15_000_000.0
    assert "updatedAt" in body
