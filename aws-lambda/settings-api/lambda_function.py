import json
import hmac
import hashlib
import time
import urllib.request
import urllib.error
from datetime import datetime
from decimal import Decimal

import boto3

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("btc-dca-settings")

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}

GMO_PRIVATE = "https://api.coin.z.com/private"
GMO_PUBLIC = "https://api.coin.z.com/public"


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
    item = table.get_item(Key={"userId": "user1"}).get("Item") or {}
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


def lambda_handler(event, context):
    method = event.get("httpMethod", "")
    path = event.get("resource") or event.get("path", "")

    if method == "OPTIONS":
        return {"statusCode": 200, "headers": HEADERS, "body": ""}

    if path.endswith("/balance"):
        if method == "GET":
            return _handle_balance()
        return _json_response(405, {"message": "Method Not Allowed"})

    if method == "GET":
        response = table.get_item(Key={"userId": "user1"})
        item = response.get("Item", {})
        return _json_response(200, item)

    if method == "POST":
        body = json.loads(event["body"])
        item = {"userId": "user1"}
        for key in ["amount", "frequency", "scheduleDay", "scheduleTime", "apiKey", "apiSecret"]:
            val = body.get(key)
            if val is not None and val != "":
                item[key] = val
        table.put_item(Item=item)
        return _json_response(200, {"message": "saved"})

    return _json_response(405, {"message": "Method Not Allowed"})
