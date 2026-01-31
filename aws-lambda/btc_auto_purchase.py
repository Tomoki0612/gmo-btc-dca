import json
import hmac
import hashlib
import time
import requests
import os
import boto3
from datetime import datetime

# 環境変数から取得
API_KEY = os.environ.get('GMO_API_KEY')
API_SECRET = os.environ.get('GMO_API_SECRET')
SNS_TOPIC_ARN = os.environ.get('SNS_TOPIC_ARN') 
INVESTMENT_AMOUNT = os.environ.get('INVESTMENT_AMOUNT')# 積立金額（円）(3000あれば賈える)

# SNSクライアントの初期化
sns = boto3.client('sns', region_name='ap-northeast-1')  # 東京リージョン

# APIキーとシークレットキーが設定されているか確認
if not API_KEY or not API_SECRET:
    raise ValueError("GMO_API_KEY または GMO_API_SECRET が環境変数に設定されていません。")

if not INVESTMENT_AMOUNT:
    raise ValueError("金額が設定されていません")

INVESTMENT_AMOUNT = int(INVESTMENT_AMOUNT)

# APIキーとシークレットキーを出力（セキュリティ上の理由から一部のみ表示）
'''
print(f"APIキー: {API_KEY[:5]}...{API_KEY[-5:]}")
print(f"シークレットキー: {API_SECRET[:5]}...{API_SECRET[-5:]}")
'''

def send_notification(subject, message):
    """SNSでメール通知を送信"""
    if not SNS_TOPIC_ARN:
        print("SNS_TOPIC_ARNが設定されていないため、通知をスキップします")
        return
    
    try:
        response = sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
        print(f"通知送信成功: MessageId={response['MessageId']}")
    except Exception as e:
        print(f"通知送信エラー: {str(e)}")

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
        
        # 買付余力（availableAmount）を取得
        available_amount = float(response_data['data'].get('availableAmount', 0))
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
        return float(data['data'][0]['last'])
    except requests.exceptions.RequestException as e:
        print(f"価格取得エラー: {str(e)}")
        raise

def place_order(amount_jpy):
    """注文を実行する関数"""
    # BTCの現在価格を取得
    btc_price = get_btc_price()
    
    # 指定円分のBTCを計算
    size = round(amount_jpy / btc_price, 5)  # 小数点以下5桁に丸める
        
    timestamp = '{0}000'.format(int(time.mktime(datetime.now().timetuple())))
    method = 'POST'
    endPoint = 'https://api.coin.z.com/private'
    path = '/v1/order'
    reqBody = {
        "symbol": "BTC",
        "side": "BUY",
        "executionType": "MARKET",
        "size": str(size)
    }
    
    text = timestamp + method + path + json.dumps(reqBody)
    sign = hmac.new(bytes(API_SECRET.encode('ascii')), bytes(text.encode('ascii')), hashlib.sha256).hexdigest()
    
    headers = {
        "API-KEY": API_KEY,
        "API-TIMESTAMP": timestamp,
        "API-SIGN": sign
    }
    
    try:
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
            return response_data, btc_price, size
            
    except requests.exceptions.Timeout:
        print("APIリクエストがタイムアウトしました")
        raise
    except requests.exceptions.RequestException as e:
        print(f"API通信エラー: {str(e)}")
        raise
    except json.JSONDecodeError:
        print("JSONデコードエラー: APIレスポンスの解析に失敗しました")
        raise

def lambda_handler(event, context):
    """Lambda関数のメインハンドラー"""
    
    try:
        
        
        print(f"積立開始: {datetime.now().isoformat()}")
        print(f"積立金額: ¥{INVESTMENT_AMOUNT:,}")
        
        # 注文実行
        result, btc_price, btc_amount = place_order(INVESTMENT_AMOUNT)
        
        # 購入後の買付余力を取得
        time.sleep(2)  # API実行後、残高反映まで少し待つ
        available_balance = get_account_balance()
        
        # 成功メッセージ
        balance_info = f"\n購入後の買付余力: ¥{available_balance:,.0f}" if available_balance is not None else "\n買付余力: 取得できませんでした"
        
        message = f"""BTC積立が成功しました

日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}
積立金額: ¥{INVESTMENT_AMOUNT:,}
BTC価格: ¥{btc_price:,.0f}
購入数量: {btc_amount} BTC
購入金額: ¥{btc_price * btc_amount:,.0f}{balance_info}

注文ID: {result.get('data', 'N/A')}
"""
        print(message)
        
        # メール通知送信（成功）
        send_notification(
            subject="BTC積立成功",
            message=message
        )
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': '積立成功',
                'amount_jpy': INVESTMENT_AMOUNT,
                'btc_price': btc_price,
                'btc_amount': btc_amount,
                'response': result
            }, ensure_ascii=False)
        }
            
    except Exception as e:
        error_message = f"""BTC積立でエラーが発生しました

日時: {datetime.now().strftime('%Y年%m月%d日 %H:%M:%S')}
エラー内容: {str(e)}

詳細はCloudWatch Logsを確認してください。
"""
        print(f"エラー発生: {str(e)}")
        
        # メール通知送信（エラー）
        send_notification(
            subject="BTC積立エラー",
            message=error_message
        )
        
        return {
            'statusCode': 500,
            'body': json.dumps({
                'message': 'エラー',
                'error': str(e)
            }, ensure_ascii=False)
        }