import requests
import json
import hmac
import hashlib
import time
import os
from datetime import datetime

# .envファイルを読み込む
#load_dotenv()

# 環境変数からAPIキーとシークレットキーを取得
API_KEY = os.environ.get('GMO_API_KEY')
API_SECRET = os.environ.get('GMO_API_SECRET')

# APIキーとシークレットキーが設定されているか確認
if not API_KEY or not API_SECRET:
    raise ValueError("GMO_API_KEY または GMO_API_SECRET が環境変数に設定されていません。")

# APIキーとシークレットキーを出力（セキュリティ上の理由から一部のみ表示）
print(f"APIキー: {API_KEY[:5]}...{API_KEY[-5:]}")
print(f"シークレットキー: {API_SECRET[:5]}...{API_SECRET[-5:]}")

# BTCの現在価格を取得する関数
def get_btc_price():
    response = requests.get('https://api.coin.z.com/public/v1/ticker?symbol=BTC')
    data = response.json()
    return float(data['data'][0]['last'])

# 30000円分のBTCを計算
btc_price = get_btc_price()
amount_jpy = 30000
size = round(amount_jpy / btc_price, 5)  # 小数点以下5桁に丸める

timestamp = '{0}000'.format(int(time.mktime(datetime.now().timetuple())))
method    = 'POST'
endPoint  = 'https://api.coin.z.com/private'
path      = '/v1/order'
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

res = requests.post(endPoint + path, headers=headers, data=json.dumps(reqBody))
print (json.dumps(res.json(), indent=2))