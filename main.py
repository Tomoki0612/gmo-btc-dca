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
    try:
        response = requests.get('https://api.coin.z.com/public/v1/ticker?symbol=BTC', timeout=30)
        response.raise_for_status()  # ステータスコードが200以外の場合は例外を発生
        data = response.json()
        return float(data['data'][0]['last'])
    except requests.exceptions.RequestException as e:
        print(f"価格取得エラー: {str(e)}")
        raise

# 10000円分のBTCを計算
btc_price = get_btc_price()

# BTCの現在価格を取得する関数
def get_btc_price():
    try:
        response = requests.get('https://api.coin.z.com/public/v1/ticker?symbol=BTC', timeout=30)
        response.raise_for_status()  # ステータスコードが200以外の場合は例外を発生
        data = response.json()
        return float(data['data'][0]['last'])
    except requests.exceptions.RequestException as e:
        print(f"価格取得エラー: {str(e)}")
        raise

# 10000円分のBTCを計算
btc_price = get_btc_price()
amount_jpy = 10000

# 10000円分のBTCを計算
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

try:
    res = requests.post(
        endPoint + path,
        headers=headers,
        data=json.dumps(reqBody),
        timeout=30  # タイムアウトを30秒に設定
    )
    res.raise_for_status()  # HTTPエラーがある場合は例外を発生
    
    response_data = res.json()
    # GMO APIの応答ステータスを確認
    if response_data.get('status') != 0:
        print(f"取引エラー: {response_data.get('messages', '不明なエラー')}")
    else:
        print("取引が正常に完了しました")
        print(json.dumps(response_data, indent=2, ensure_ascii=False))

except requests.exceptions.Timeout:
    print("APIリクエストがタイムアウトしました")
except requests.exceptions.RequestException as e:
    print(f"API通信エラー: {str(e)}")
except json.JSONDecodeError:
    print("JSONデコードエラー: APIレスポンスの解析に失敗しました")
except Exception as e:
    print(f"予期せぬエラーが発生しました: {str(e)}")