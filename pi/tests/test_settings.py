def test_get_settings_empty(conn):
    from pi.api.settings import get_settings

    assert get_settings(conn) == {}


def test_upsert_partial_then_diff_history(conn):
    from pi.api.settings import get_settings, list_history, upsert_settings

    upsert_settings(
        conn,
        {
            "amount": 1000,
            "frequency": "monthly",
            "scheduleDay": 5,
            "scheduleTime": 9,
            "apiKey": "k1",
            "apiSecret": "s1",
        },
    )
    s = get_settings(conn)
    assert s["amount"] == 1000
    assert s["frequency"] == "monthly"
    assert s["scheduleDay"] == 5
    assert s["scheduleTime"] == 9
    assert s["apiKey"] == "k1"
    assert s["apiSecret"] == "s1"

    # Empty / None values must NOT clobber existing fields.
    upsert_settings(conn, {"amount": 2000, "apiKey": "", "apiSecret": None})
    s2 = get_settings(conn)
    assert s2["amount"] == 2000
    assert s2["apiKey"] == "k1"
    assert s2["apiSecret"] == "s1"

    # First upsert created 4 change rows (amount, schedule, time, api).
    # Second upsert created 1 change row (amount).
    history = list_history(conn)
    fields = [h["field"] for h in history if h["type"] == "change"]
    assert fields.count("amount") == 2
    assert fields.count("schedule") == 1
    assert fields.count("time") == 1
    assert fields.count("api") == 1


def test_upsert_no_diff_no_history(conn):
    from pi.api.settings import list_history, upsert_settings

    upsert_settings(conn, {"amount": 500, "frequency": "daily", "scheduleTime": 10})
    upsert_settings(conn, {"amount": 500, "frequency": "daily", "scheduleTime": 10})
    history = [h for h in list_history(conn) if h["type"] == "change"]
    # First call wrote amount, schedule, time. Second call wrote nothing.
    assert len(history) == 3


def test_already_purchased_today(conn):
    from pi.api.settings import already_purchased_today, put_purchase

    assert already_purchased_today(conn) is False
    put_purchase(conn, status="ok", amount_jpy=1000, btc=0.001, rate=1_000_000)
    assert already_purchased_today(conn) is True


def test_failed_purchase_does_not_count(conn):
    from pi.api.settings import already_purchased_today, put_purchase

    put_purchase(conn, status="failed", amount_jpy=1000, reason="boom")
    assert already_purchased_today(conn) is False
