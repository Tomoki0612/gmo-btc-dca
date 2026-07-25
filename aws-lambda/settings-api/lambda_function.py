import json
import hmac
import hashlib
import time
import uuid
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("btc-dca-settings")
history_table = dynamodb.Table("btc-dca-history")
ssm = boto3.client("ssm")

GMO_API_CREDENTIALS_PARAMETER = os.environ.get(
    "GMO_API_CREDENTIALS_PARAMETER", "/gmo-btc-dca/prod/gmo-api-credentials"
)

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
}

GMO_PRIVATE = "https://api.coin.z.com/private"
GMO_PUBLIC = "https://api.coin.z.com/public"

JST = timezone(timedelta(hours=9))

USER_ID = "user1"

FREQ_LABEL = {"daily": "毎日", "weekly": "毎週", "monthly": "毎月"}
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]


def _get_secure_parameter(name):
    try:
        return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ParameterNotFound":
            return None
        raise


def _load_api_credentials(item):
    """SSMを優先し、未移行の場合だけDynamoDBの旧フィールドを読む。"""
    value = _get_secure_parameter(GMO_API_CREDENTIALS_PARAMETER)
    if value:
        try:
            credentials = json.loads(value)
            api_key = credentials["apiKey"]
            api_secret = credentials["apiSecret"]
        except (json.JSONDecodeError, KeyError, TypeError):
            raise RuntimeError("SSMのGMO API認証情報の形式が正しくありません")
        if not api_key or not api_secret:
            raise RuntimeError("SSMのGMO API認証情報が不足しています")
        return api_key, api_secret, "ssm"

    legacy_key = item.get("apiKey")
    legacy_secret = item.get("apiSecret")
    if legacy_key and legacy_secret:
        return legacy_key, legacy_secret, "dynamodb"
    return None, None, None


def _put_api_credentials(api_key, api_secret):
    ssm.put_parameter(
        Name=GMO_API_CREDENTIALS_PARAMETER,
        Value=json.dumps({"apiKey": api_key, "apiSecret": api_secret}),
        Type="SecureString",
        Tier="Standard",
        Overwrite=True,
    )


def _public_settings(item, api_configured):
    public = {
        key: value
        for key, value in item.items()
        if key not in {"apiKey", "apiSecret"}
    }
    public["apiConfigured"] = api_configured
    return public


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
    try:
        api_key, api_secret, _ = _load_api_credentials(item)
    except Exception as e:
        return _json_response(502, {"configured": False, "message": f"認証情報の取得エラー: {e}"})

    # 公開ティッカーは認証不要なので API キー有無に関わらず取得を試みる
    try:
        rate = _fetch_btc_price()
    except Exception:
        rate = None

    if not api_key or not api_secret:
        return _json_response(200, {"configured": False, "btcJpyRate": rate})

    try:
        assets = _fetch_assets(api_key, api_secret)
    except urllib.error.HTTPError as e:
        return _json_response(502, {"configured": True, "btcJpyRate": rate, "message": f"GMOコインAPIエラー ({e.code})"})
    except Exception as e:
        return _json_response(502, {"configured": True, "btcJpyRate": rate, "message": str(e)})

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


def _diff_and_record(old, new, old_api_configured=False, new_api_configured=False):
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

    if old_api_configured != new_api_configured:
        _put_history_change(
            "api",
            "設定済み" if old_api_configured else "未設定",
            "設定済み" if new_api_configured else "未設定",
        )


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
        try:
            api_key, api_secret, _ = _load_api_credentials(item)
        except Exception as e:
            return _json_response(502, {"message": f"認証情報の取得エラー: {e}"})
        return _json_response(200, _public_settings(item, bool(api_key and api_secret)))

    if method == "POST":
        try:
            body = json.loads(event.get("body") or "{}")
        except json.JSONDecodeError:
            return _json_response(400, {"message": "JSON形式が正しくありません"})

        existing = table.get_item(Key={"userId": USER_ID}).get("Item") or {}
        try:
            old_key, old_secret, credential_source = _load_api_credentials(existing)
        except Exception as e:
            return _json_response(502, {"message": f"認証情報の取得エラー: {e}"})

        new_key = str(body.get("apiKey") or "").strip()
        new_secret = str(body.get("apiSecret") or "").strip()
        if bool(new_key) != bool(new_secret):
            return _json_response(400, {"message": "APIキーとAPIシークレットを両方入力してください"})

        try:
            if new_key and new_secret:
                _put_api_credentials(new_key, new_secret)
                final_key, final_secret = new_key, new_secret
            elif credential_source == "dynamodb":
                # 旧DynamoDB値を初回の設定保存時にSecureStringへ移行する。
                _put_api_credentials(old_key, old_secret)
                final_key, final_secret = old_key, old_secret
            else:
                final_key, final_secret = old_key, old_secret
        except Exception as e:
            return _json_response(502, {"message": f"認証情報の保存エラー: {e}"})

        item = {
            key: value
            for key, value in existing.items()
            if key not in {"apiKey", "apiSecret"}
        }
        item["userId"] = USER_ID
        for key in ["amount", "frequency", "scheduleDay", "scheduleTime"]:
            if key not in body:
                continue
            val = body.get(key)
            if val is None or val == "":
                item.pop(key, None)
            else:
                item[key] = val

        try:
            table.put_item(Item=item)
        except Exception as e:
            return _json_response(502, {"message": f"設定の保存エラー: {e}"})

        new_api_configured = bool(final_key and final_secret)
        try:
            _diff_and_record(
                existing,
                item,
                old_api_configured=bool(old_key and old_secret),
                new_api_configured=new_api_configured,
            )
        except Exception as e:  # noqa: BLE001
            print(f"diff record failed: {e}")
        return _json_response(200, {
            "message": "saved",
            "apiConfigured": new_api_configured,
        })

    return _json_response(405, {"message": "Method Not Allowed"})
