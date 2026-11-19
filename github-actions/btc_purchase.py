import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN

import requests


PRIVATE_API = "https://api.coin.z.com/private"
TICKER_URL = "https://api.coin.z.com/public/v1/ticker"
BTC_ORDER_STEP = Decimal("0.00001")
TIMEOUT = (5, 15)


def purchase_period(instant, frequency):
    instant = instant.astimezone(timezone.utc)
    if frequency == "monthly":
        return instant.strftime("%Y%m")
    if frequency == "weekly":
        return (instant - timedelta(days=instant.weekday())).strftime("%Y%m%d")
    if frequency == "daily":
        return instant.strftime("%Y%m%d")
    if frequency == "hourly":
        return instant.strftime("%Y%m%d%H")
    raise ValueError("注文の頻度が不正です")


def client_order_id(repository_id, created_at, frequency, now):
    period = purchase_period(created_at, frequency)
    if period != purchase_period(now, frequency):
        raise ValueError("積立期間を過ぎた実行です")
    # The repository ID survives renames, and GitHub preserves the original
    # creation time across attempts. The exchange enforces ID uniqueness.
    seed = f"gmo-btc-dca:github:{repository_id}:{frequency}:{period}"
    return hashlib.sha256(seed.encode("ascii")).hexdigest()[:32]


def private_json(method, path, api_key, api_secret, *, body=None, params=None):
    timestamp = str(time.time_ns() // 1_000_000)
    payload = json.dumps(body) if body is not None else ""
    sign = hmac.new(
        api_secret.encode("ascii"),
        f"{timestamp}{method}{path}{payload}".encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    response = requests.request(
        method,
        PRIVATE_API + path,
        params=params,
        data=payload if body is not None else None,
        headers={
            "API-KEY": api_key,
            "API-TIMESTAMP": timestamp,
            "API-SIGN": sign,
            "Content-Type": "application/json",
        },
        timeout=TIMEOUT,
        allow_redirects=False,
    )
    if response.status_code != 200:
        raise requests.HTTPError()
    return response.json()


def get_btc_price():
    response = requests.get(
        TICKER_URL, params={"symbol": "BTC"}, timeout=TIMEOUT, allow_redirects=False
    )
    if response.status_code != 200:
        raise requests.HTTPError()
    payload = response.json()
    if payload["status"] != 0:
        raise ValueError("BTC価格の取得に失敗しました")
    price = Decimal(payload["data"][0]["last"])
    if not price.is_finite() or price <= 0:
        raise ValueError("BTC価格が不正です")
    return price


def confirm_order(order_id, api_key, api_secret):
    try:
        response = private_json(
            "GET", "/v1/orders", api_key, api_secret, params={"clientOrderId": order_id}
        )
        if response["status"] == 0 and any(
            order.get("clientOrderId") == order_id for order in response["data"]["list"]
        ):
            print("同じ顧客注文IDの注文を確認しました。約定状況はGMOコインで確認してください。")
            return 0
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError):
        pass
    print("注文結果を確認できませんでした。GMOコインの注文履歴を確認してください。")
    return 1


def place_order(amount, order_id, api_key, api_secret):
    size = (Decimal(amount) / get_btc_price()).quantize(BTC_ORDER_STEP, rounding=ROUND_DOWN)
    if size < BTC_ORDER_STEP:
        print("注文数量がBTCの最小注文数量を下回っています。")
        return 1

    try:
        response = private_json(
            "POST",
            "/v1/order",
            api_key,
            api_secret,
            body={
                "symbol": "BTC",
                "side": "BUY",
                "executionType": "MARKET",
                "size": format(size, "f"),
                "clientOrderId": order_id,
            },
        )
        if response["status"] == 0:
            if response.get("data"):
                print("注文が受理されました。")
                return 0
        elif not any(message.get("message_code") == "ERR-915" for message in response["messages"]):
            print("注文が拒否されました。GMOコインの設定や残高を確認してください。")
            return 1
    except (requests.RequestException, ValueError, TypeError, KeyError, AttributeError):
        pass
    # A timeout or a duplicate ID can mean the original order was accepted.
    # Only look up the result here. Never submit another POST from this run.
    return confirm_order(order_id, api_key, api_secret)


def main():
    try:
        api_key = os.environ["GMO_API_KEY"]
        api_secret = os.environ["GMO_API_SECRET"]
        repository_id = os.environ["GITHUB_REPOSITORY_ID"]
        created_at = datetime.fromisoformat(os.environ["DCA_RUN_CREATED_AT"].replace("Z", "+00:00"))
        amount = int(os.environ["INVESTMENT_AMOUNT"])
        if not api_key or not api_secret or not repository_id.isascii() or not repository_id.isdecimal():
            raise ValueError
        if created_at.tzinfo is None or not 1000 <= amount <= 500000:
            raise ValueError
        order_id = client_order_id(
            repository_id,
            created_at,
            os.environ.get("DCA_ORDER_FREQUENCY") or "monthly",
            datetime.now(timezone.utc),
        )
    except (KeyError, ValueError):
        print("認証情報、積立金額、実行日時または積立頻度が不正です。")
        return 1

    try:
        return place_order(amount, order_id, api_key, api_secret)
    except (requests.RequestException, ValueError, TypeError, KeyError, IndexError, InvalidOperation):
        print("注文前の価格取得または数量計算に失敗しました。")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
