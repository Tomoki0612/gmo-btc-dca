# GMO BTC 自動積立システム

GMOコインのAPIを使ってビットコイン（BTC）を自動積立するシステムです。

## 機能

- 毎月28日にBTCを自動購入
- 成行注文
- エラー時の通知機能（Lambda版）

## 実行環境の選択

このシステムは2つの実行環境に対応しています：

### 1. GitHub Actions

**メリット:**
- 無料
- セットアップが簡単
- GitHubアカウントだけで完結

**デメリット:**
- エラー通知機能なし
- カスタマイズの自由度が低い

[セットアップ手順](github-actions/README.md)

### 2. AWS Lambda（上級者向け）

**メリット:**
- メール通知機能あり（SNS連携）
- AWSの他サービスと連携可能
- より高度なカスタマイズが可能
- ほぼ無料（月100万リクエストまで無料）

**デメリット:**
- AWSアカウントが必要
- セットアップがやや複雑

[セットアップ手順](aws-lambda/README.md)

## 前提条件

### 共通
1. GMOコインのアカウント
2. GMOコインのAPIキー・シークレットキー

### GitHub Actions
- GitHubアカウント

### AWS Lambda
- AWSアカウント
- AWS CLI（オプション）

## GMO APIキーの取得方法

1. GMOコインにログイン
2. 「口座情報」→「APIキー管理」
3. 「新しいAPIキーを発行」
4. 必要な権限を選択（**取引**権限が必要）
5. APIキーとシークレットキーをメモ

**重要**: シークレットキーは他の人に見せないでください

## 積立金額の設定

デフォルトは **10,000円/月** です。

### 変更方法

#### GitHub Actions
GitHub Actionsのsecretsにて、INVESTMENT_AMOUNT値を変更

#### AWS Lambda
環境変数のINVESTMENT_AMOUNTの値を変更

## 実行スケジュールの変更

### GitHub Actions
`.github/workflows/bitcoin_dca.yml` のcron式を編集：
```yaml
schedule:
  - cron: '0 0 28 * *'  # 毎月28日UTC 0時 = JST 9時
```

cron式の例：
- `0 0 * * *` - 毎日0時（UTC）= 毎日9時（JST）
- `0 */12 * * *` - 12時間ごと
- `0 0 * * 1` - 毎週月曜日0時

### AWS Lambda
EventBridgeルールのcron式を変更：
```
cron(0 0 28 * ? *)  # 毎月28日UTC 0時 = JST 9時
```

## 実行ログの確認

### GitHub Actions
1. GitHubリポジトリ > Actions タブ
2. 実行履歴を確認

### AWS Lambda
1. Lambda関数 > Monitor タブ > View logs in CloudWatch
2. 最新のログストリームを確認

## 注意事項

- **APIキーは絶対に公開しないでください**
- **少額からテストすることを推奨します**
- GMOコインの口座に十分な残高があることを確認してください(最低3000円程度あれば購入できます)
- 投資は自己責任でお願いします

## セキュリティ

- APIキーは環境変数で管理
- GitHubの場合はSecretsに保存
- AWSの場合はLambda環境変数に保存
- コードにAPIキーを直接書き込まない

## 免責事項

このシステムを使用したことによる損失について、開発者は一切の責任を負いません。投資は自己責任で行ってください。

