# AWSバックエンド（SAM）

BTC自動積立のAWSバックエンドは、`template.yaml` と
CloudFormationスタック `btc-auto-purchase` で一括管理します。

## SAMで管理するリソース

- `btc-auto-purchase` Lambda
- `btc-dca-settings-api` Lambda
- API Gateway（`/settings`、`/balance`、`/history`）
- Cognito User PoolとSPAクライアント
- DynamoDB（`btc-dca-settings`、`btc-dca-history`）
- DynamoDB（`btc-dca-executions`、同一時間帯の重複注文防止用）
- EventBridgeの定期実行
- SNSトピックとメール購読
- Lambda実行ロールとAPI呼び出し権限

GMO APIキーとシークレットは、CloudFormationテンプレートへ値を入れません。
SSM Parameter Store StandardのSecureString
`/gmo-btc-dca/prod/gmo-api-credentials` に保存し、SAMから名前だけを参照します。

Discord Webhook URLも同様に、Standard SecureString
`/gmo-btc-dca/prod/discord-webhook-url`へ保存します。購入成功・失敗はDiscordへ通知し、
Discordが未設定または送信失敗の場合だけSNSメールへフォールバックします。

Webhook URLは画面やGitへ貼らず、ローカル端末で次のコマンドを実行して登録します。

```bash
make configure-discord
make test-discord
```

`make configure-discord`はURLを非表示で入力し、SecureStringへ保存します。
`make test-discord`は購入処理を実行せず、通知だけを送信します。

既存のDynamoDB、Cognito、設定Lambda、IAMロールは2026-07-25に同じスタックへ
CloudFormation Import済みです。テーブルとCognitoには`Retain`を設定しているため、
スタック操作で既存履歴やログインユーザーを削除しません。

## 通常のデプロイ

前提:

- AWS CLIがログイン済み
- AWS SAM CLIがインストール済み
- `ap-northeast-1`へのデプロイ権限がある

新しい環境では、秘密情報を含まないサンプルから設定ファイルを作成します。

```bash
cd aws-lambda
cp samconfig.toml.example samconfig.toml
# NotificationEmail、DryRun、AuthorizedUserSub、FrontendOriginを確認
make validate
make deploy
```

`AuthorizedUserSub` は、この単一ユーザーアプリへのアクセスを許可するCognitoユーザーの
`sub`です。別のユーザーのIDトークンはAPIが403で拒否します。次のコマンドで確認できます。

```bash
aws cognito-idp list-users \
  --user-pool-id <UserPoolId> \
  --query 'Users[].Attributes[?Name==`sub`].Value' \
  --output text \
  --region ap-northeast-1
```

`FrontendOrigin` は末尾スラッシュなしの実際のフロントURLを指定します。APIのCORSは
このオリジンだけを許可します。

`make deploy`は次を一括で実行します。

1. Python 3.12向けに両Lambdaをビルド
2. CloudFormation変更セットを表示
3. 確認後、スタックを更新

環境・通知先・スケジュール・DryRunは`samconfig.toml`で管理します。
秘密情報は`samconfig.toml`へ書かないでください。

## Outputs

```bash
make outputs
```

主なOutput:

| Output | 用途 |
|---|---|
| `ApiBaseUrl` | フロントの`REACT_APP_API_BASE_URL` |
| `UserPoolId` | フロントの`REACT_APP_COGNITO_USER_POOL_ID` |
| `UserPoolClientId` | フロントの`REACT_APP_COGNITO_USER_POOL_CLIENT_ID` |
| `SettingsTableName` | 設定テーブル |
| `HistoryTableName` | 履歴テーブル |
| `ExecutionTableName` | 重複注文防止・注文状態テーブル |

## ローカル確認

```bash
make validate
make build
make invoke
```

`make invoke`には`auto-purchase/env.json`が必要です。テンプレートは構文検証に加えて
`sam validate --lint`を実行します。

## ログ

```bash
make logs-auto
make logs-settings
```

## 注文の安全性

- EventBridgeの同一JST時間枠はDynamoDBの条件付き書き込みで一度だけ実行します。
- BTC数量は取引所現物の注文単位`0.00001 BTC`へ切り捨てます。
- 成行注文後に注文・約定APIを照会し、実約定数量、加重平均価格、手数料を履歴へ保存します。
- 注文送信時のタイムアウトなど、成立有無を断定できないケースは`pending`（要確認）として
  保存します。この場合は自動再注文しません。GMOコインの注文履歴とCloudWatch Logsを確認してください。
- 設定APIは金額、頻度、日付、時刻をサーバー側でも検証します。

`btc-dca-executions`はオンデマンドテーブルで、ロック項目はTTLにより約90日後に削除されます。
追加の常時稼働サービスはありません。

## 削除について

DynamoDB、Cognito、設定Lambda、設定LambdaのIAMロールには`Retain`を設定しています。
それでもスタック削除はAPI Gateway、購入Lambda、EventBridge、SNSなどを削除するため、
通常運用では`sam delete`を実行しないでください。
