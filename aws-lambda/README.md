# AWS Lambda デプロイ手順

## 前提条件
- AWSアカウント
- AWS CLI設定済み
- GMOコインAPIキー・シークレット

## デプロイ方法

### 方法1: AWS コンソールから（初心者向け）

#### 1. Lambda関数の作成
1. AWSコンソールにログイン
2. Lambda > 関数 > 関数の作成
3. 「一から作成」を選択
   - 関数名: `btc-auto-purchase`
   - ランタイム: Python 3.11
   - 実行ロール: 新しいロールを作成（基本的なLambda権限）
4. 「関数の作成」をクリック

#### 2. コードのアップロード
1. `lambda_function.py` の内容をコピー
2. Lambdaコンソールのコードエディタに貼り付け
3. 「Deploy」をクリック

#### 3. Lambdaレイヤーの追加（requests用）
requestsライブラリはデフォルトで含まれていないため、レイヤーを追加：

**オプションA: 公開レイヤーを使用**
1. Lambda関数 > レイヤー > レイヤーの追加
2. 「ARNを指定」を選択
3. 以下のARNを入力（東京リージョンの場合）:
   ```
   arn:aws:lambda:ap-northeast-1:770693421928:layer:Klayers-p311-requests:8
   ```

**オプションB: 自分でレイヤーを作成**
```bash
cd aws-lambda
mkdir python
pip install -r requirements.txt -t python/
zip -r requests-layer.zip python
```
その後、AWSコンソールでレイヤーを作成してアップロード

#### 4. 環境変数の設定
1. Lambda関数 > 設定 > 環境変数
2. 以下を追加:
   - `GMO_API_KEY`: あなたのAPIキー
   - `GMO_API_SECRET`: あなたのシークレットキー
   - `SNS_TOPIC_ARN`: （オプション）通知用のSNS Topic ARN

#### 5. タイムアウト設定
1. Lambda関数 > 設定 > 一般設定 > 編集
2. タイムアウト: `30秒`
3. メモリ: `256 MB`

#### 6. EventBridgeスケジュール設定
1. EventBridge > ルール > ルールを作成
2. ルールタイプ: スケジュール
3. スケジュールパターン:
   - Cron式: `0 0 * * ? *` （毎日UTC 0時 = JST 9時）
4. ターゲット: Lambda関数 > `btc-auto-purchase`
5. 作成

### 方法2: AWS CLI（上級者向け）

#### 1. デプロイパッケージの作成
```bash
cd aws-lambda

# 依存関係をインストール
mkdir package
pip install -r requirements.txt -t package/

# ZIPファイルを作成
cd package
zip -r ../lambda_deployment.zip .
cd ..
zip -g lambda_deployment.zip lambda_function.py
```

#### 2. IAMロールの作成
```bash
# ロールのポリシードキュメントを作成
cat > trust-policy.json << EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
EOF

# ロールを作成
aws iam create-role \
  --role-name btc-lambda-execution-role \
  --assume-role-policy-document file://trust-policy.json

# 基本的な実行権限を付与
aws iam attach-role-policy \
  --role-name btc-lambda-execution-role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# SNS権限を付与（通知を使う場合）
aws iam attach-role-policy \
  --role-name btc-lambda-execution-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonSNSFullAccess
```

#### 3. Lambda関数の作成
```bash
# ロールのARNを取得（YOUR_ACCOUNT_IDを自分のIDに置き換え）
ROLE_ARN="arn:aws:iam::YOUR_ACCOUNT_ID:role/btc-lambda-execution-role"

# Lambda関数を作成
aws lambda create-function \
  --function-name btc-auto-purchase \
  --runtime python3.11 \
  --role $ROLE_ARN \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda_deployment.zip \
  --timeout 30 \
  --memory-size 256 \
  --region ap-northeast-1
```

#### 4. 環境変数の設定
```bash
aws lambda update-function-configuration \
  --function-name btc-auto-purchase \
  --environment Variables="{GMO_API_KEY=your_api_key,GMO_API_SECRET=your_api_secret}" \
  --region ap-northeast-1

# SNS通知を使う場合は追加
aws lambda update-function-configuration \
  --function-name btc-auto-purchase \
  --environment Variables="{GMO_API_KEY=your_api_key,GMO_API_SECRET=your_api_secret,SNS_TOPIC_ARN=your_topic_arn}" \
  --region ap-northeast-1
```

#### 5. EventBridgeスケジュールの作成
```bash
# Lambda関数に権限を付与
aws lambda add-permission \
  --function-name btc-auto-purchase \
  --statement-id AllowEventBridgeInvoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --region ap-northeast-1

# EventBridgeルールを作成
aws events put-rule \
  --name btc-daily-purchase \
  --schedule-expression "cron(0 0 * * ? *)" \
  --region ap-northeast-1

# ターゲットを設定
aws events put-targets \
  --rule btc-daily-purchase \
  --targets "Id"="1","Arn"="arn:aws:lambda:ap-northeast-1:YOUR_ACCOUNT_ID:function:btc-auto-purchase" \
  --region ap-northeast-1
```

## SNS通知の設定（オプション）

成功・失敗時にメール通知を受け取る場合：

### 1. SNSトピックの作成
```bash
aws sns create-topic --name btc-purchase-notifications --region ap-northeast-1
```

### 2. メールアドレスを登録
```bash
aws sns subscribe \
  --topic-arn arn:aws:sns:ap-northeast-1:YOUR_ACCOUNT_ID:btc-purchase-notifications \
  --protocol email \
  --notification-endpoint your@email.com \
  --region ap-northeast-1
```

### 3. 確認メールをチェック
メールボックスを確認し、購読を承認

### 4. LambdaにTopic ARNを設定
環境変数 `SNS_TOPIC_ARN` に上記のARNを設定

## テスト実行

### コンソールから
1. Lambda関数 > テスト
2. テストイベント名: `test-event`
3. イベントJSON: `{}`（空で良い）
4. 「テスト」をクリック

### CLIから
```bash
aws lambda invoke \
  --function-name btc-auto-purchase \
  --payload '{}' \
  --region ap-northeast-1 \
  response.json

cat response.json
```

## トラブルシューティング

### CloudWatch Logsの確認
```bash
aws logs tail /aws/lambda/btc-auto-purchase --follow --region ap-northeast-1
```

### よくあるエラー

**エラー: "Unable to import module 'lambda_function'"**
→ requestsライブラリが見つからない。レイヤーを追加してください。

**エラー: "Task timed out after 3.00 seconds"**
→ タイムアウト設定を30秒に増やしてください。

**エラー: "GMO_API_KEY が環境変数に設定されていません"**
→ 環境変数が正しく設定されているか確認してください。

## コスト

- Lambda: 月100万リクエストまで無料（1日1回なら完全無料）
- EventBridge: 無料枠内
- CloudWatch Logs: 5GBまで無料
- SNS: 月1,000件まで無料

**月額コスト: ほぼ¥0**

## セキュリティ

- APIキーは環境変数で管理
- IAMロールは最小権限の原則
- CloudWatch Logsで実行履歴を確認可能