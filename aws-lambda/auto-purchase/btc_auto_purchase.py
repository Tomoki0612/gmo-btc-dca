import json
import hmac
import hashlib
import time
import uuid
import requests
import os
import boto3
from botocore.exceptions import ClientError
from botocore.config import Config
from boto3.dynamodb.conditions import Attr
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN
from urllib.parse import urlparse

JST = timezone(timedelta(hours=9))
AWS_CONFIG = Config(connect_timeout=2, read_timeout=3, retries={"total_max_attempts": 1})
_context = None


class ExecutionBudgetExceeded(Exception):
    """Stop optional network work while there is still time to persist the result."""


def _remaining_seconds():
    return _context.get_remaining_time_in_millis() / 1000 if _context else 120


def _http_timeout(reserve=30):
    # requests has separate connect/read limits, not an overall invocation deadline.
    available = min(8, _remaining_seconds() - reserve)
    if available < 2:
        raise ExecutionBudgetExceeded("実行時間が少ないため通信を中断しました")
    return (min(2, available / 2), available - min(2, available / 2))

# DynamoDB クライアントの初期化
dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1", config=AWS_CONFIG)
table = dynamodb.Table("btc-dca-settings")
history_table = dynamodb.Table("btc-dca-history")
execution_table = dynamodb.Table(
    os.environ.get("EXECUTION_TABLE_NAME", "btc-dca-executions")
)
ssm = boto3.client("ssm", config=AWS_CONFIG)
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN')
DRY_RUN = os.environ.get('DRY_RUN')
GMO_API_CREDENTIALS_PARAMETER = os.environ.get(
    "GMO_API_CREDENTIALS_PARAMETER", "/gmo-btc-dca/prod/gmo-api-credentials"
)
DISCORD_WEBHOOK_PARAMETER = os.environ.get(
    "DISCORD_WEBHOOK_PARAMETER", "/gmo-btc-dca/prod/discord-webhook-url"
)

USER_ID = "user1"
BTC_ORDER_STEP = Decimal("0.00001")


class DuplicateExecution(Exception):
    """The current schedule slot has already been claimed."""


class OrderReconciliationError(Exception):
    """An order was accepted but its final executions could not be confirmed."""

    def __init__(self, order_id, message):
        super().__init__(message)
        self.order_id = order_id


class OrderSubmissionUncertain(Exception):
    """The exchange may have accepted an order although the response was lost."""


class OrderNotFilled(Exception):
    """The exchange confirmed a terminal order with zero executed quantity."""


def _get_secure_parameter(name):
    try:
        return ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ParameterNotFound":
            return None
        raise


def _get_api_credentials(settings):
    """SSMを優先し、移行期間中のみDynamoDBの旧データへフォールバックする。"""
    value = _get_secure_parameter(GMO_API_CREDENTIALS_PARAMETER)
    if value:
        try:
            credentials = json.loads(value)
            api_key = credentials["apiKey"]
            api_secret = credentials["apiSecret"]
        except (json.JSONDecodeError, KeyError, TypeError):
            raise ValueError("SSMのGMO API認証情報の形式が正しくありません")
        if not api_key or not api_secret:
            raise ValueError("SSMのGMO API認証情報が不足しています")
        return api_key, api_secret

    legacy_key = settings.get("apiKey")
    legacy_secret = settings.get("apiSecret")
    if legacy_key and legacy_secret:
        print("警告: DynamoDBの旧API認証情報を使用しています。設定画面から再保存してください")
        return legacy_key, legacy_secret
    return None, None


def _put_purchase_history(
    status,
    amount_jpy,
    btc=None,
    rate=None,
    reason=None,
    order_id=None,
    fee=None,
    requested_amount=None,
    history_key=None,
    history_at=None,
):
    """積立実行の履歴を DynamoDB に記録する。"""
    ts = int(time.time() * 1000)
    sk = history_key or f"{ts:013d}#purchase#{uuid.uuid4().hex[:6]}"
    item = {
        "userId": USER_ID,
        "sk": sk,
        "id": sk,
        "type": "purchase",
        "at": history_at or datetime.now(JST).isoformat(timespec="seconds"),
        "status": status,
        "amount": int(amount_jpy) if amount_jpy is not None else None,
    }
    if btc is not None:
        item["btc"] = Decimal(str(round(float(btc), 8)))
    if rate is not None:
        item["rate"] = Decimal(str(round(float(rate), 2)))
    if reason:
        item["reason"] = str(reason)[:200]
    if order_id is not None:
        item["orderId"] = str(order_id)
    if fee is not None:
        item["fee"] = Decimal(str(fee))
    if requested_amount is not None:
        item["requestedAmount"] = int(requested_amount)

    clean = {k: v for k, v in item.items() if v is not None}
    history_table.put_item(Item=clean)


def _execution_key(now):
    return f"{USER_ID}#{now.strftime('%Y-%m-%dT%H:00%z')}"


def _acquire_execution(now, amount=0):
    """Claim one JST schedule slot atomically before any order is submitted."""
    key = _execution_key(now)
    record = {
        "executionKey": key,
        "status": "started",
        "startedAt": now.isoformat(timespec="seconds"),
        "expiresAt": int(now.timestamp()) + 90 * 24 * 60 * 60,
        "requestedAmount": amount,
        "historySk": f"{int(now.timestamp() * 1000):013d}#purchase#{key}",
    }
    try:
        execution_table.put_item(
            Item=record,
            ConditionExpression="attribute_not_exists(executionKey)",
        )
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise DuplicateExecution(key) from e
        raise
    return record


def _update_execution(key, status, **values):
    names = {"#status": "status"}
    attrs = {":status": status, ":updatedAt": datetime.now(JST).isoformat(timespec="seconds")}
    assignments = ["#status = :status", "updatedAt = :updatedAt"]
    for index, (name, value) in enumerate(values.items()):
        token = f":value{index}"
        names[f"#field{index}"] = name
        attrs[token] = value
        assignments.append(f"#field{index} = {token}")
    execution_table.update_item(
        Key={"executionKey": key},
        UpdateExpression="SET " + ", ".join(assignments),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=attrs,
    )


def _validate_purchase_settings(settings):
    try:
        amount = int(settings["amount"])
        frequency = settings["frequency"]
        schedule_time = int(settings["scheduleTime"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("積立設定が不足または不正です")

    if not 1000 <= amount <= 500000:
        raise ValueError("積立金額は1,000円以上500,000円以下にしてください")
    if frequency not in {"daily", "weekly", "monthly"}:
        raise ValueError("積立頻度が不正です")
    if not 0 <= schedule_time <= 23:
        raise ValueError("積立時間は0〜23時で指定してください")

    schedule_day = settings.get("scheduleDay")
    if frequency == "weekly":
        try:
            schedule_day = int(schedule_day)
        except (TypeError, ValueError):
            raise ValueError("曜日を指定してください")
        if not 1 <= schedule_day <= 7:
            raise ValueError("曜日は1〜7で指定してください")
    elif frequency == "monthly":
        try:
            schedule_day = int(schedule_day)
        except (TypeError, ValueError):
            raise ValueError("日付を指定してください")
        if not 1 <= schedule_day <= 28:
            raise ValueError("日付は1〜28で指定してください")
    else:
        schedule_day = None

    return amount, frequency, schedule_day, schedule_time

# SNSクライアントの初期化
sns = boto3.client('sns', region_name='ap-northeast-1', config=AWS_CONFIG)

def _log_notification_error(channel, error):
    # requests exceptions can contain the full secret webhook URL. Never log their text.
    status = getattr(getattr(error, "response", None), "status_code", None)
    detail = f" (HTTP {status})" if isinstance(status, int) and 100 <= status <= 599 else ""
    print(f"{channel}通知送信エラー: {type(error).__name__}{detail}")


def send_notification(subject, message):
    """Discordへ通知し、送信できない場合だけSNSメールへフォールバックする。"""
    try:
        webhook_url = _get_secure_parameter(DISCORD_WEBHOOK_PARAMETER)
        if webhook_url:
            parsed = urlparse(webhook_url)
            if (
                parsed.scheme != "https"
                or parsed.hostname not in {"discord.com", "discordapp.com"}
                or not parsed.path.startswith("/api/webhooks/")
            ):
                raise ValueError("Discord Webhook URLの形式が正しくありません")

            content = f"**{subject}**\n\n{message}"
            response = requests.post(
                webhook_url,
                json={
                    "content": content[:2000],
                    "allowed_mentions": {"parse": []},
                },
                timeout=_http_timeout(reserve=8),
            )
            response.raise_for_status()
            print("Discord通知送信成功")
            return True
        print("Discord Webhookが未設定のため、メール通知へフォールバックします")
    except Exception as e:
        _log_notification_error("Discord", e)

    if not SNS_TOPIC_ARN:
        print("SNS_TOPIC_ARNが設定されていないため、フォールバック通知をスキップします")
        return False

    try:
        response = sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
        print(f"メール通知送信成功: MessageId={response['MessageId']}")
        return True
    except Exception as e:
        _log_notification_error("メール", e)
        return False

def get_account_balance():
    """口座残高（買付余力）を取得する関数"""
    timestamp = '{0}000'.format(int(time.mktime(datetime.now().timetuple())))
    method = 'GET'
    endPoint = 'https://api.coin.z.com/private'
    path = '/v1/account/margin'
    
    text = timestamp + method + path
    sign = hmac.new(bytes(API_SECRET.encode('ascii')), bytes(text.encode('ascii')), hashlib.sha256).hexdigest()
    
    headers = {
        "API-KEY": API_KEY,
        "API-TIMESTAMP": timestamp,
        "API-SIGN": sign
    }
    
    try:
        res = requests.get(
            endPoint + path,
            headers=headers,
            timeout=_http_timeout()
        )
        res.raise_for_status()
        
        response_data = res.json()
        
        if response_data.get('status') != 0:
            error_msg = f"残高取得エラー: {response_data.get('messages', '不明なエラー')}"
            print(error_msg)
            return None
        
        # 現物買付余力を取得（旧API応答との互換性のためavailableAmountへフォールバック）
        available_amount = float(
            response_data['data'].get(
                'availableAmountForSpot',
                response_data['data'].get('availableAmount', 0),
            )
        )
        return available_amount
        
    except Exception as e:
        print(f"残高取得エラー: {str(e)}")
        return None

def get_btc_price():
    """BTCの現在価格を取得する関数"""
    try:
        response = requests.get('https://api.coin.z.com/public/v1/ticker?symbol=BTC', timeout=_http_timeout())
        response.raise_for_status() # ステータスコードが200以外の場合は例外を発生
        data = response.json()
        return Decimal(str(data['data'][0]['last']))
    except requests.exceptions.RequestException as e:
        print(f"価格取得エラー: {str(e)}")
        raise

def place_order(amount_jpy):
    """注文を実行する関数"""
    # BTCの現在価格を取得
    btc_price = get_btc_price()
    
    # 指定円分のBTCを計算
    size = (Decimal(amount_jpy) / btc_price).quantize(BTC_ORDER_STEP, rounding=ROUND_DOWN)
    if size < BTC_ORDER_STEP:
        raise ValueError("注文数量がBTCの最小注文数量を下回っています")
        
    timestamp = '{0}000'.format(int(time.mktime(datetime.now().timetuple())))
    method = 'POST'
    endPoint = 'https://api.coin.z.com/private'
    path = '/v1/order'
    reqBody = {
        "symbol": "BTC",
        "side": "BUY",
        "executionType": "MARKET",
        "size": format(size, "f")
    }
    
    text = timestamp + method + path + json.dumps(reqBody)
    sign = hmac.new(bytes(API_SECRET.encode('ascii')), bytes(text.encode('ascii')), hashlib.sha256).hexdigest()
    
    headers = {
        "API-KEY": API_KEY,
        "API-TIMESTAMP": timestamp,
        "API-SIGN": sign
    }
    
    try:
        if DRY_RUN == "true":
            return "DRY_RUN", btc_price, size
        else:
            res = requests.post(
                endPoint + path,
                headers=headers,
                data=json.dumps(reqBody),
                timeout=_http_timeout()
            )
        res.raise_for_status()
        
        response_data = res.json()

        # GMO APIの応答ステータスを確認        
        if response_data.get('status') != 0:
            error_msg = f"取引エラー: {response_data.get('messages', '不明なエラー')}"
            print(error_msg)
            raise Exception(error_msg)
        else:
            print("取引が正常に完了しました")
            print(json.dumps(response_data, indent=2, ensure_ascii=False))
            order_id = response_data.get("data")
            if not order_id:
                raise OrderSubmissionUncertain(
                    "注文は受理されましたが注文IDを取得できませんでした。約定有無の確認が必要です"
                )
            return str(order_id), btc_price, size
            
    except requests.exceptions.Timeout as e:
        print("APIリクエストがタイムアウトしました")
        raise OrderSubmissionUncertain("注文応答がタイムアウトしました。約定有無の確認が必要です") from e
    except requests.exceptions.RequestException as e:
        print(f"API通信エラー: {str(e)}")
        raise OrderSubmissionUncertain("注文送信中に通信エラーが発生しました。約定有無の確認が必要です") from e
    except json.JSONDecodeError as e:
        print("JSONデコードエラー: APIレスポンスの解析に失敗しました")
        raise OrderSubmissionUncertain(
            "注文応答を解析できませんでした。約定有無の確認が必要です"
        ) from e


def _private_get(path, params):
    timestamp = str(int(time.time() * 1000))
    sign = hmac.new(
        API_SECRET.encode("ascii"),
        f"{timestamp}GET{path}".encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    response = requests.get(
        f"https://api.coin.z.com/private{path}",
        headers={
            "API-KEY": API_KEY,
            "API-TIMESTAMP": timestamp,
            "API-SIGN": sign,
        },
        params=params,
        timeout=_http_timeout(),
    )
    response.raise_for_status()
    data = response.json()
    if data.get("status") != 0:
        raise RuntimeError(f"GMO APIエラー: {data.get('messages', '不明なエラー')}")
    return data.get("data", {})


def _wait_for_execution(order_id, attempts=5, delay=1):
    """Return actual filled size, weighted rate, and fee for a market FAK order."""
    for attempt in range(attempts):
        order_data = _private_get("/v1/orders", {"orderId": order_id})
        orders = order_data.get("list", [])
        status = orders[0].get("status") if orders else None

        execution_data = _private_get("/v1/executions", {"orderId": order_id})
        executions = execution_data.get("list", [])
        if executions and status in {"EXECUTED", "CANCELED", "EXPIRED"}:
            filled = sum((Decimal(str(row["size"])) for row in executions), Decimal("0"))
            gross = sum(
                (Decimal(str(row["size"])) * Decimal(str(row["price"])) for row in executions),
                Decimal("0"),
            )
            fee = sum((Decimal(str(row.get("fee", "0"))) for row in executions), Decimal("0"))
            if filled <= 0:
                break
            return {
                "btc": filled,
                "rate": gross / filled,
                "gross": gross,
                "fee": fee,
                "orderStatus": status,
            }
        if status in {"CANCELED", "EXPIRED"}:
            if Decimal(str(orders[0].get("executedSize", "-1"))) == 0:
                raise OrderNotFilled(f"注文 {order_id} は未約定で終了しました ({status})")
            break
        if attempt + 1 < attempts:
            time.sleep(delay)
    raise OrderReconciliationError(order_id, f"注文 {order_id} の約定結果を確認できませんでした")

def _record_history(record, status, order_id=None, execution=None, reason=None):
    values = {}
    amount = record["requestedAmount"]
    if execution is not None:
        amount = int((execution["gross"] + execution["fee"]).to_integral_value())
        values = {"btc": execution["btc"], "rate": execution["rate"], "fee": execution["fee"]}
    _put_purchase_history(
        status=status,
        amount_jpy=amount,
        order_id=order_id,
        requested_amount=record["requestedAmount"],
        history_key=record["historySk"],
        history_at=record["startedAt"],
        reason=reason,
        **values,
    )


def _complete_purchase(record, order_id, execution):
    # Persist before balance lookups or notifications. Repeated reconciliation replaces
    # this same row, so a crash between these writes cannot double the purchase total.
    _record_history(record, "ok", order_id=order_id, execution=execution)
    _update_execution(
        record["executionKey"], "succeeded", orderId=order_id,
        executedBtc=execution["btc"], actualAmount=execution["gross"] + execution["fee"],
        notificationPending=True,
    )


def _notify_result(record, subject, message):
    try:
        if send_notification(subject=subject, message=message):
            execution_table.update_item(
                Key={"executionKey": record["executionKey"]},
                UpdateExpression="SET notificationPending = :pending",
                ExpressionAttributeValues={":pending": False},
            )
    except Exception as e:
        # Keep the durable outcome intact; the reconciliation job retries notification.
        print(f"通知の送信または送信状態の保存に失敗: {e}")


def _success_message(record, order_id, btc, actual_amount):
    balance_info = ""
    if _remaining_seconds() > 50:
        try:
            available_balance = get_account_balance()
            if available_balance is not None:
                balance_info = f"\n購入後の買付余力: ¥{available_balance:,.0f}"
        except Exception as e:
            print(f"購入後の残高取得をスキップ: {e}")
    return (
        f"BTC積立が成功しました\n\n日時: {record['startedAt']}\n"
        f"設定金額: ¥{record['requestedAmount']:,}\n購入数量: {btc} BTC\n"
        f"約定金額（手数料込み）: ¥{actual_amount:,.0f}\n注文ID: {order_id}{balance_info}"
    )


def _reconcile_pending():
    """Recover stale executions without ever submitting an order."""
    if DRY_RUN == "true":
        return {"statusCode": 200, "body": "DRY_RUNでは本番注文を照合しません"}
    settings = table.get_item(Key={"userId": USER_ID}).get("Item") or {}
    global API_KEY, API_SECRET
    API_KEY, API_SECRET = _get_api_credentials(settings)
    if not API_KEY or not API_SECRET:
        raise ValueError("APIキーが設定されていません")

    cutoff = (datetime.now(JST) - timedelta(minutes=5)).isoformat(timespec="seconds")
    pending = Attr("status").is_in(["started", "submitting", "ordered", "reconciliation_pending"])
    pending = pending | Attr("notificationPending").eq(True)
    kwargs = {
        "FilterExpression": pending & Attr("startedAt").lt(cutoff) & Attr("historySk").exists(),
        "Limit": 100,
    }
    while _remaining_seconds() > 55:
        page = execution_table.scan(**kwargs)
        for record in page.get("Items", []):
            if _remaining_seconds() <= 55:
                return {"statusCode": 200, "body": "残りの照合は次回実行します"}
            key = record["executionKey"]
            # A lease prevents overlapping reconciliation invocations from writing
            # conflicting results. It expires after the Lambda's 120-second limit.
            try:
                claimed = execution_table.update_item(
                    Key={"executionKey": key},
                    UpdateExpression="SET reconcileUntil = :until",
                    ConditionExpression=(
                        "attribute_exists(executionKey) AND "
                        "(attribute_not_exists(reconcileUntil) OR reconcileUntil < :now)"
                    ),
                    ExpressionAttributeValues={":until": int(time.time()) + 180, ":now": int(time.time())},
                    ReturnValues="ALL_NEW",
                )
                record = claimed["Attributes"]
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                    continue
                raise
            try:
                status = record["status"]
                order_id = record.get("orderId")
                if status == "succeeded":
                    if record.get("notificationPending"):
                        _notify_result(record, "BTC積立成功", _success_message(
                            record, order_id, record["executedBtc"], record["actualAmount"],
                        ))
                    continue
                if status in {"failed", "manual_required"}:
                    if record.get("notificationPending"):
                        _notify_result(record, "BTC積立 要確認" if status == "manual_required" else "BTC積立エラー",
                                       record.get("reason", "注文履歴を確認してください"))
                    continue
                if not order_id:
                    reason = "注文IDが保存されていません。GMOコインの注文履歴を確認してください。自動再注文は行いません"
                    _record_history(record, "pending", reason=reason)
                    _update_execution(key, "manual_required", reason=reason, notificationPending=True)
                    _notify_result(record, "BTC積立 要確認", reason)
                    continue
                execution = _wait_for_execution(order_id, attempts=1)
                _complete_purchase(record, order_id, execution)
                _notify_result(record, "BTC積立成功", _success_message(
                    record, order_id, execution["btc"], execution["gross"] + execution["fee"],
                ))
            except OrderNotFilled as e:
                _record_history(record, "failed", order_id=order_id, reason=str(e))
                _update_execution(key, "failed", reason=str(e), notificationPending=True)
                _notify_result(record, "BTC積立エラー", str(e))
            except Exception as e:
                # Existing pending history remains visible; retry on the next schedule.
                print(f"注文照合を次回へ持ち越します ({key}): {e}")
                if status not in {"succeeded", "failed", "manual_required"}:
                    if status != "reconciliation_pending":
                        _update_execution(key, "reconciliation_pending", reason=str(e)[:200], notificationPending=True)
                        _notify_result(record, "BTC積立 要確認", str(e))
                    elif record.get("notificationPending"):
                        _notify_result(record, "BTC積立 要確認", str(e))
        if not page.get("LastEvaluatedKey"):
            break
        kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    return {"statusCode": 200, "body": "注文照合完了"}


def lambda_handler(event, context):
    """Lambda関数のメインハンドラー"""
    global _context
    _context = context
    if event.get("action") == "test-notification":
        send_notification(subject="BTC積立 通知テスト", message="Discord通知の設定が完了しました。")
        return {"statusCode": 200, "body": "通知テスト完了"}
    if event.get("action") == "reconcile":
        return _reconcile_pending()

    record = None
    order_id = None
    investment_amount = None
    completed = False
    try:
        settings = table.get_item(Key={"userId": USER_ID}).get("Item")
        if not settings:
            raise ValueError("設定が見つかりません")
        investment_amount, frequency, schedule_day, schedule_time = _validate_purchase_settings(settings)
        now = datetime.now(JST)
        if now.hour != schedule_time:
            return {"statusCode": 200, "body": "スキップ（時間外）"}
        if frequency == "weekly" and now.weekday() + 1 != schedule_day:
            return {"statusCode": 200, "body": "スキップ（曜日外）"}
        if frequency == "monthly" and now.day != schedule_day:
            return {"statusCode": 200, "body": "スキップ（日付外）"}

        global API_KEY, API_SECRET
        API_KEY, API_SECRET = _get_api_credentials(settings)
        if not API_KEY or not API_SECRET:
            raise ValueError("APIキーが設定されていません")

        if DRY_RUN == "true":
            # Simulation has no purchase history, execution lock, or private order calls.
            _, quoted_price, requested_btc = place_order(investment_amount)
            send_notification(
                subject="BTC積立 テスト完了（DRY_RUN）",
                message=f"実注文は行っていません。設定金額: ¥{investment_amount:,} / 参考数量: {requested_btc} BTC",
            )
            return {"statusCode": 200, "body": json.dumps({
                "message": "テスト完了（実注文なし）", "dry_run": True,
                "estimated_btc": str(requested_btc), "quoted_price": str(quoted_price),
            }, ensure_ascii=False)}

        if _remaining_seconds() < 55:
            raise ExecutionBudgetExceeded("注文と記録に必要な実行時間が不足しています")
        record = _acquire_execution(now, investment_amount)
        # This must succeed before the POST. Even a hard Lambda timeout then leaves
        # a visible pending row and enough metadata for later reconciliation.
        _record_history(record, "pending", reason="注文処理中です。結果が未確定のため再注文しないでください")
        _update_execution(record["executionKey"], "submitting")
        order_id, _, _ = place_order(investment_amount)
        _update_execution(record["executionKey"], "ordered", orderId=order_id)
        _record_history(record, "pending", order_id=order_id, reason="約定結果を確認中です")
        execution = _wait_for_execution(order_id)
        _complete_purchase(record, order_id, execution)
        completed = True
        actual_amount = execution["gross"] + execution["fee"]
        _notify_result(record, "BTC積立成功", _success_message(
            record, order_id, execution["btc"], actual_amount,
        ))
        return {"statusCode": 200, "body": json.dumps({
            "message": "積立成功", "amount_jpy": int(actual_amount.to_integral_value()),
            "btc_price": str(execution["rate"]), "btc_amount": str(execution["btc"]), "order_id": order_id,
        }, ensure_ascii=False)}

    except DuplicateExecution as e:
        print(f"重複実行をスキップ: {e}")
        return {"statusCode": 200, "body": "スキップ（実行済み）"}
    except Exception as e:
        print(f"エラー発生: {e}")
        ambiguous = not isinstance(e, OrderNotFilled) and (
            order_id is not None or isinstance(e, OrderSubmissionUncertain)
        )
        reason = str(e)[:200]
        subject = "BTC積立 要確認" if ambiguous else "BTC積立エラー"
        if DRY_RUN == "true":
            subject = "BTC積立 テストエラー（DRY_RUN）"
        elif not completed:
            try:
                if record:
                    _record_history(record, "pending" if ambiguous else "failed", order_id=order_id, reason=reason)
                    _update_execution(
                        record["executionKey"], "reconciliation_pending" if ambiguous else "failed",
                        **({"orderId": order_id} if order_id else {}), reason=reason, notificationPending=True,
                    )
                else:
                    _put_purchase_history(status="failed", amount_jpy=investment_amount, reason=reason)
            except Exception as persistence_error:
                print(f"実行結果の保存に失敗（定期照合で再確認します）: {persistence_error}")
        if record:
            _notify_result(record, subject, reason)
        else:
            send_notification(subject=subject, message=reason)
        return {"statusCode": 500, "body": json.dumps({"message": "エラー", "error": reason}, ensure_ascii=False)}
