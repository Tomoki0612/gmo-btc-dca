import os
import sys
import time
import hmac
import hashlib
import json
import logging
import requests
from datetime import datetime
import math

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

logging.info("プログラムが開始されました")

# 環境変数から認証情報を取得
API_KEY = os.environ.get('GMO_API_KEY')
API_SECRET = os.environ.get('GMO_API_SECRET')

if not API_KEY or not API_SECRET:
    logging.error("GMO_API_KEY or GMO_API_SECRET is not set in the environment variables.")
    sys.exit(1)

logging.info(f"API_KEY: {API_KEY[:5]}...")  # セキュリティのため、最初の5文字のみ表示

# 設定
TEST_MODE = False  # 実際の取引を行うためFalseに設定
TRADE_AMOUNT = 30000  # 30,000円の取引に設定
API_ENDPOINT = 'https://api.coin.z.com'

def get_signature(method, endpoint, body):
    timestamp = str(time.time())
    message = timestamp + method + endpoint + body
    signature = hmac.new(API_SECRET.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
    return signature, timestamp

def place_market_order(amount):
    method = 'POST'
    endpoint = '/private/v1/account/orders'
    body = json.dumps({
        "symbol": "BTC_JPY",
        "side": "BUY",
        "executionType": "MARKET",
        "size": str(amount / 1000000)  # 取引金額をBTCに変換
    })
    signature, timestamp = get_signature(method, endpoint, body)
    headers = {
        'API-KEY': API_KEY,
        'API-TIMESTAMP': timestamp,
        'API-SIGN': signature,
        'Content-Type': 'application/json'
    }
    response = requests.post(API_ENDPOINT + endpoint, headers=headers, data=body)
    return response.json()

def get_btc_price():
    logging.info("ビットコイン価格を取得します")
    response = requests.get(API_ENDPOINT + '/public/v1/ticker?symbol=BTC_JPY')
    data = response.json()
    if 'data' in data and len(data['data']) > 0:
        price = float(data['data'][0]['last'])
        logging.info(f"現在のビットコイン価格: {price} JPY")
        return price
    else:
        logging.error("ビットコイン価格の取得に失敗しました")
        raise ValueError("ビットコイン価格の取得に失敗しました")

def main():
    logging.info("main関数が開始されました")
    try:
        btc_price = get_btc_price()
        amount = TRADE_AMOUNT / btc_price
        # 0.00000001 BTC単位に丸める
        amount = round(amount, 8)
        logging.info(f"購入予定量: {amount} BTC")
        result = place_market_order(amount)
        logging.info(f"注文結果: {result}")
    except Exception as e:
        logging.error(f"エラーが発生しました: {str(e)}", exc_info=True)
    logging.info("プログラムが終了しました")

if __name__ == "__main__":
    main()