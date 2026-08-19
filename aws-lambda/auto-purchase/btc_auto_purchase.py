import json
import hmac
import hashlib
import time
import uuid
import requests
import os
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_DOWN
from urllib.parse import urlparse

JST = timezone(timedelta(hours=9))

# DynamoDB クライアントの初期化
dynamodb = boto3.resource("dynamodb", region_name="ap-northeast-1")
table = dynamodb.Table("btc-dca-settings")
history_table = dynamodb.Table("btc-dca-history")
execution_table = dynamodb.Table(
    os.environ.get("EXECUTION_TABLE_NAME", "btc-dca-executions")
)
ssm = boto3.client("ssm")
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
):
    """積立実行の履歴を DynamoDB に記録する。"""
    ts = int(time.time() * 1000)
    sk = f"{ts:013d}#purchase#{uuid.uuid4().hex[:6]}"
    item = {
        "userId": USER_ID,
        "sk": sk,
        "id": sk,
        "type": "purchase",
        "at": datetime.now(JST).isoformat(timespec="seconds"),
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
    try:
        history_table.put_item(Item=clean)
    except Exception as e:
        print(f"購入履歴の保存に失敗: {e}")


def _execution_key(now):
    return f"{USER_ID}#{now.strftime('%Y-%m-%dT%H:00%z')}"


def _acquire_execution(now):
    """Claim one JST schedule slot atomically before any order is submitted."""
    key = _execution_key(now)
    try:
        execution_table.put_item(
            Item={
                "executionKey": key,
                "status": "started",
                "startedAt": now.isoformat(timespec="seconds"),
                "expiresAt": int(now.timestamp()) + 90 * 24 * 60 * 60,
            },
            ConditionExpression="attribute_not_exists(executionKey)",
        )
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise DuplicateExecution(key) from e
        raise
    return key


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
sns = boto3.client('sns', region_name='ap-northeast-1')  # 東京リージョン

# APIキーとシークレットキーを出力（セキュリティ上の理由から一部のみ表示）
'''
print(f"APIキー: {API_KEY[:5]}...{API_KEY[-5:]}")
print(f"シークレットキー: {API_SECRET[:5]}...{API_SECRET[-5:]}")
'''

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
                timeout=10,
            )
            response.raise_for_status()
            print("Discord通知送信成功")
            return
        print("Discord Webhookが未設定のため、メール通知へフォールバックします")
    except Exception as e:
        print(f"Discord通知送信エラー: {str(e)}")

    if not SNS_TOPIC_ARN:
        print("SNS_TOPIC_ARNが設定されていないため、フォールバック通知をスキップします")
        return

    try:
        response = sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
        print(f"メール通知送信成功: MessageId={response['MessageId']}")
    except Exception as e:
        print(f"メール通知送信エラー: {str(e)}")

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
            timeout=30
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
        response = requests.get('https://api.coin.z.com/public/v1/ticker?symbol=BTC', timeout=30)
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
                timeout=30
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
        timeout=10,
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
            break
        if attempt + 1 < attempts:
            time.sleep(delay)
    raise OrderReconciliationError(order_id, f"注文 {order_id} の約定結果を確認できませんでした")

def lambda_handler(event, context):
    """Lambda関数のメインハンドラー"""
    if event.get("action") == "test-notification":
        send_notification(
            subject="BTC積立 通知テスト",
            message="Discord通知の設定が完了しました。",
        )
        return {"statusCode": 200, "body": "通知テスト完了"}

    execution_key = None
    order_id = None
    investment_amount = None
    try:
        # DynamoDBから設定を取得
        response = table.get_item(Key={"userId": "user1"})
        settings = response.get("Item")
        if not settings:
            raise ValueError("設定が見つかりません")

        global API_KEY, API_SECRET
        API_KEY, API_SECRET = _get_api_credentials(settings)
        investment_amount, frequency, schedule_day, schedule_time = _validate_purchase_settings(settings)
        now = datetime.now(JST)

        if now.hour != schedule_time:
            print(f"実行時間外: 現在{now.hour}時 / 設定{schedule_time}時")
            return {"statusCode": 200, "body": "スキップ（時間外）"}

        if frequency == "weekly":
            # Python: 月=0, 火=1 ... 日=6
            # DynamoDB: 月=1, 火=2 ... 日=7
            if now.weekday() + 1 != schedule_day:
                print(f"実行曜日外: 現在{now.weekday()+1} / 設定{schedule_day}")
                return {"statusCode": 200, "body": "スキップ（曜日外）"}

        elif frequency == "monthly":
            if now.day != schedule_day:
                print(f"実行日外: 現在{now.day}日 / 設定{schedule_day}日")
                return {"statusCode": 200, "body": "スキップ（日付外）"}

        # daily の場合は時間が合えばそのまま実行

        if not API_KEY or not API_SECRET:
            raise ValueError("APIキーが設定されていません")
        execution_key = _acquire_execution(now)

        print(f"積立開始: {datetime.now(JST).isoformat()}")    
        print(f"積立金額: ¥{investment_amount:,}")
        
        # 注文実行
        _update_execution(execution_key, "submitting")
        order_id, quoted_price, requested_btc = place_order(investment_amount)
        _update_execution(execution_key, "ordered", orderId=order_id)

        if DRY_RUN == "true":
            execution = {
                "btc": requested_btc,
                "rate": quoted_price,
                "gross": requested_btc * quoted_price,
                "fee": Decimal("0"),
                "orderStatus": "DRY_RUN",
            }
        else:
            execution = _wait_for_execution(order_id)

        btc_amount = execution["btc"]
        btc_price = execution["rate"]
        fee = execution["fee"]
        actual_amount = execution["gross"] + fee
        _update_execution(
            execution_key,
            "succeeded",
            orderId=order_id,
            executedBtc=btc_amount,
            actualAmount=actual_amount,
        )
        
        # 購入後の買付余力を取得
        time.sleep(2)  # API実行後、残高反映まで少し待つ
        available_balance = get_account_balance()
        
        # 成功メッセージ
        balance_info = f"\n購入後の買付余力: ¥{available_balance:,.0f}" if available_balance is not None else "\n買付余力: 取得できませんでした"
        
        message = f"""BTC積立が成功しました

日時: {datetime.now(JST).strftime('%Y年%m月%d日 %H:%M:%S')}
設定金額: ¥{investment_amount:,}
BTC価格: ¥{btc_price:,.0f}
購入数量: {btc_amount} BTC
約定金額: ¥{execution['gross']:,.0f}
取引手数料: ¥{fee:,.0f}{balance_info}

注文ID: {order_id}
"""
        print(message)
        
        # 履歴を保存（成功）
        _put_purchase_history(
            status="ok",
            amount_jpy=int(actual_amount.to_integral_value()),
            btc=btc_amount,
            rate=btc_price,
            order_id=order_id,
            fee=fee,
            requested_amount=investment_amount,
        )

        # メール通知送信（成功）
        send_notification(
            subject="BTC積立成功",
            message=message
        )

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': '積立成功',
                'amount_jpy': int(actual_amount.to_integral_value()),
                'btc_price': str(btc_price),
                'btc_amount': str(btc_amount),
                'order_id': order_id,
            }, ensure_ascii=False)
        }

    except DuplicateExecution as e:
        print(f"重複実行をスキップ: {e}")
        return {"statusCode": 200, "body": "スキップ（実行済み）"}

    except Exception as e:
        ambiguous = DRY_RUN != "true" and (
            order_id is not None or isinstance(e, OrderSubmissionUncertain)
        )
        history_status = "pending" if ambiguous else "failed"
        if execution_key:
            try:
                _update_execution(
                    execution_key,
                    "reconciliation_pending" if ambiguous else "failed",
                    **({"orderId": order_id} if order_id else {}),
                    reason=str(e)[:200],
                )
            except Exception as update_error:
                print(f"実行状態の更新に失敗: {update_error}")
        error_message = f"""BTC積立でエラーが発生しました

日時: {datetime.now(JST).strftime('%Y年%m月%d日 %H:%M:%S')}
エラー内容: {str(e)}

詳細はCloudWatch Logsを確認してください。
"""
        print(f"エラー発生: {str(e)}")

        # 履歴を保存（失敗）— スケジュールスキップ以外の本処理エラーのみ
        _put_purchase_history(
            status=history_status,
            amount_jpy=investment_amount,
            reason=str(e),
            order_id=order_id,
            requested_amount=investment_amount,
        )

        # メール通知送信（エラー）
        send_notification(
            subject="BTC積立 要確認" if ambiguous else "BTC積立エラー",
            message=error_message
        )

        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'エラー',
                'error': str(e)
            }, ensure_ascii=False)
        }
