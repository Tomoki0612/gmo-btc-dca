import requests
import json
from datetime import datetime
import time
import hmac
import hashlib
import os
import logging
from dotenv import load_dotenv
import math

print("プログラムが開始されました")

# .envファイルから環境変数を読み込む
load_dotenv()
print(f"API_KEY: {os.getenv('API_KEY')[:5]}...")  # セキュリティのため、最初の5文字のみ表示

# ロギングの設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
print("ロギングが設定されました")

# 設定
TEST_MODE = False  # 実際の取引を行うためFalseに設定
TRADE_AMOUNT = 10000  # 10,000円の取引に設定

API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
API_ENDPOINT = 'https://api.bitflyer.com'

def get_signature(method, endpoint, body):
    timestamp = str(time.time())
    message = timestamp + method + endpoint + body
    signature = hmac.new(API_SECRET.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).hexdigest()
    return signature, timestamp

def place_market_order(amount):
    method = 'POST'
    endpoint = '/v1/me/sendchildorder'
    body = json.dumps({
        "product_code": "BTC_JPY",
        "child_order_type": "MARKET",
        "side": "BUY",
        "size": amount,
    })

    signature, timestamp = get_signature(method, endpoint, body)

    headers = {
        'ACCESS-KEY': API_KEY,
        'ACCESS-TIMESTAMP': timestamp,
        'ACCESS-SIGN': signature,
        'Content-Type': 'application/json'
    }

    if TEST_MODE:
        logging.info(f"テストモード: 注文をシミュレート - {amount} BTC")
        return {"status": "TEST_SUCCESS"}

    response = requests.post(API_ENDPOINT + endpoint, headers=headers, data=body)
    return response.json()

def get_btc_price():
    print("ビットコイン価格を取得します")
    response = requests.get(API_ENDPOINT + '/v1/ticker?product_code=BTC_JPY')
    price = float(response.json()['ltp'])
    print(f"現在のビットコイン価格: {price} JPY")
    return price

def main():
    print("main関数が開始されました")
    try:
        btc_price = get_btc_price()
        amount = TRADE_AMOUNT / btc_price
        # 0.00000001 BTC単位に丸める
        amount = math.floor(amount * 100000000) / 100000000
        print(f"購入予定量: {amount} BTC")

        result = place_market_order(amount)
        print(f"注文結果: {result}")

    except Exception as e:
        print(f"エラーが発生しました: {str(e)}")

    print("プログラムが終了しました")

if __name__ == "__main__":
    main()