import json
import hmac
import hashlib
import time
import uuid
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("btc-dca-settings")
history_table = dynamodb.Table("btc-dca-history")

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

GMO_PRIVATE = "https://api.coin.z.com/private"
GMO_PUBLIC = "https://api.coin.z.com/public"

JST = timezone(timedelta(hours=9))

USER_ID = "user1"

FREQ_LABEL = {"daily": "毎日", "weekly": "毎週", "monthly": "毎月"}
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]


def decimal_to_num(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    raise TypeError


def _json_response(status, body):
    return {
        "statusCode": status,
        "headers": HEADERS,
        "body": json.dumps(body, default=decimal_to_num),
    }


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


def _handle_balance():
    item = table.get_item(Key={"userId": USER_ID}).get("Item") or {}
    api_key = item.get("apiKey")
    api_secret = item.get("apiSecret")
    if not api_key or not api_secret:
        return _json_response(200, {"configured": False})

    try:
        assets = _fetch_assets(api_key, api_secret)
        rate = _fetch_btc_price()
    except urllib.error.HTTPError as e:
        return _json_response(502, {"configured": True, "message": f"GMOコインAPIエラー ({e.code})"})
    except Exception as e:
        return _json_response(502, {"configured": True, "message": str(e)})

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

    return _json_response(200, {
        "configured": True,
        "jpy": jpy,
        "btc": btc,
        "btcJpyRate": rate,
        "updatedAt": datetime.utcnow().isoformat() + "Z",
    })


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


def _now_sk(prefix):
    ts = int(time.time() * 1000)
    return f"{ts:013d}#{prefix}#{uuid.uuid4().hex[:6]}"


def _put_history_change(field, before, after):
    sk = _now_sk("change")
    item = {
        "userId": USER_ID,
        "sk": sk,
        "id": sk,
        "type": "change",
        "at": datetime.now(JST).isoformat(timespec="seconds"),
        "field": field,
        "before": before,
        "after": after,
    }
    try:
        history_table.put_item(Item=item)
    except Exception as e:  # noqa: BLE001
        print(f"history put failed ({field}): {e}")


def _diff_and_record(old, new):
    """設定変更を項目単位で履歴に記録する。"""
    if int(old.get("amount") or 0) != int(new.get("amount") or 0):
        _put_history_change("amount", _fmt_yen(old.get("amount")), _fmt_yen(new.get("amount")))

    old_freq = old.get("frequency")
    new_freq = new.get("frequency")
    old_day = old.get("scheduleDay")
    new_day = new.get("scheduleDay")
    if old_freq != new_freq or (new_freq != "daily" and old_day != new_day):
        _put_history_change(
            "schedule",
            _fmt_schedule(old_freq, old_day),
            _fmt_schedule(new_freq, new_day),
        )

    if (old.get("scheduleTime") if old.get("scheduleTime") is not None else None) != (
        new.get("scheduleTime") if new.get("scheduleTime") is not None else None
    ):
        _put_history_change(
            "time",
            _fmt_time(old.get("scheduleTime")),
            _fmt_time(new.get("scheduleTime")),
        )

    old_api = bool(old.get("apiKey") and old.get("apiSecret"))
    new_api = bool(new.get("apiKey") and new.get("apiSecret"))
    if old_api != new_api:
        _put_history_change("api", "未設定" if not old_api else "設定済み", "設定済み" if new_api else "未設定")


def _handle_history():
    try:
        resp = history_table.query(
            KeyConditionExpression=Key("userId").eq(USER_ID),
            ScanIndexForward=False,
            Limit=200,
        )
    except Exception as e:  # noqa: BLE001
        return _json_response(502, {"message": f"履歴取得エラー: {e}"})

    items = []
    for it in resp.get("Items", []):
        row = {
            "id": it.get("id") or it.get("sk"),
            "type": it.get("type"),
            "at": it.get("at"),
        }
        t = it.get("type")
        if t == "purchase":
            row.update({
                "status": it.get("status"),
                "amount": it.get("amount"),
                "btc": it.get("btc"),
                "rate": it.get("rate"),
                "reason": it.get("reason"),
            })
        elif t == "change":
            row.update({
                "field": it.get("field"),
                "before": it.get("before"),
                "after": it.get("after"),
            })
        items.append(row)

    return _json_response(200, {"items": items})


def lambda_handler(event, context):
    method = event.get("httpMethod", "")
    path = event.get("resource") or event.get("path", "")

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": HEADERS, "body": ""}

    if path.endswith("/balance"):
        if method == "GET":
            return _handle_balance()
        return _json_response(405, {"message": "Method Not Allowed"})

    if path.endswith("/history"):
        if method == "GET":
            return _handle_history()
        return _json_response(405, {"message": "Method Not Allowed"})

    if method == "GET":
        response = table.get_item(Key={"userId": USER_ID})
        item = response.get("Item", {})
        return _json_response(200, item)

    if method == "POST":
        body = json.loads(event["body"])
        existing = table.get_item(Key={"userId": USER_ID}).get("Item") or {}
        item = {"userId": USER_ID}
        for key in ["amount", "frequency", "scheduleDay", "scheduleTime", "apiKey", "apiSecret"]:
            val = body.get(key)
            if val is not None and val != "":
                item[key] = val
        table.put_item(Item=item)
        try:
            _diff_and_record(existing, item)
        except Exception as e:  # noqa: BLE001
            print(f"diff record failed: {e}")
        return _json_response(200, {"message": "saved"})

    return _json_response(405, {"message": "Method Not Allowed"})
