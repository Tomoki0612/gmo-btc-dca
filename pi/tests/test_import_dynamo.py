"""Smoke tests for the DynamoDB JSON importer."""

import json


def _write(tmp_path, name, payload):
    p = tmp_path / name
    p.write_text(json.dumps(payload), encoding="utf-8")
    return str(p)


def test_imports_aws_typed_settings(tmp_path, db_path):
    from pi.api.db import connect
    from pi.api.settings import get_settings
    from pi.scripts.import_dynamo import main

    settings_path = _write(
        tmp_path,
        "settings.json",
        {
            "Items": [
                {
                    "userId": {"S": "user1"},
                    "amount": {"N": "5000"},
                    "frequency": {"S": "monthly"},
                    "scheduleDay": {"N": "5"},
                    "scheduleTime": {"N": "9"},
                    "apiKey": {"S": "k"},
                    "apiSecret": {"S": "s"},
                    "updatedAt": {"S": "2026-05-01T09:00:00+09:00"},
                }
            ]
        },
    )
    main(["import_dynamo", "--settings", settings_path, "--db", db_path])

    c = connect(db_path)
    try:
        s = get_settings(c)
    finally:
        c.close()
    assert s["amount"] == 5000
    assert s["frequency"] == "monthly"
    assert s["scheduleDay"] == 5


def test_imports_history_and_dedup_on_id(tmp_path, db_path):
    from pi.api.db import connect
    from pi.api.settings import list_history
    from pi.scripts.import_dynamo import main

    history_path = _write(
        tmp_path,
        "history.json",
        {
            "Items": [
                {
                    "userId": {"S": "user1"},
                    "id": {"S": "1700000000000#purchase#abc123"},
                    "type": {"S": "purchase"},
                    "at": {"S": "2026-04-05T09:00:01+09:00"},
                    "status": {"S": "ok"},
                    "amount": {"N": "1000"},
                    "btc": {"N": "0.0001"},
                    "rate": {"N": "10000000"},
                }
            ]
        },
    )
    main(["import_dynamo", "--history", history_path, "--db", db_path])
    main(["import_dynamo", "--history", history_path, "--db", db_path])  # idempotent

    c = connect(db_path)
    try:
        rows = [h for h in list_history(c) if h["type"] == "purchase"]
    finally:
        c.close()
    assert len(rows) == 1
    assert rows[0]["amount"] == 1000
    assert rows[0]["btc"] == 0.0001
