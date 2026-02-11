# GitHub Actions版 セットアップ手順

> **注意**: このGitHub Actions版は動作未確認です。
> 本システムのメインの実行環境はAWS Lambda（EventBridge経由）です。Lambda版のセットアップは [aws-lambda/README.md](../aws-lambda/README.md) を参照してください。
> GitHub Actions版はLambdaを使わない代替手段として用意しています。

GitHub Actionsを使って、毎月自動でBTCを積立購入する。

## 前提条件

1. GitHubアカウント
2. GMOコインのアカウント
3. GMOコインのAPIキー・シークレットキー

## セットアップ手順

### 1. このリポジトリをフォーク

右上の「Fork」ボタンをクリックして、自分のアカウントにコピー

### 2. GitHub Secretsを設定

1. フォークしたリポジトリに移動
2. 「Settings」タブをクリック
3. 左メニューから「Secrets and variables」>「Actions」を選択
4. 「New repository secret」をクリック

以下の3つのSecretを追加：

| Name | 値 |
|------|-----|
| `GMO_API_KEY` | GMOコインのAPIキー |
| `GMO_API_SECRET` | GMOコインのシークレットキー |
| `INVESTMENT_AMOUNT` | 積立金額（円）例: `10000` |

### 3. GitHub Actionsを有効化

1. 「Actions」タブをクリック
2. 「I understand my workflows, go ahead and enable them」をクリック

### 4. 初回実行（テスト）

1. 「Actions」タブで「Monthly BTC Purchase」をクリック
2. 「Run workflow」をクリック
3. 「Run workflow」ボタンを再度クリック

数分待って実行結果を確認。緑のチェックマークが出れば成功。

## 設定のカスタマイズ

### 積立金額を変更

GitHub Secretsの `INVESTMENT_AMOUNT` の値を変更する。

### 実行日時を変更

`.github/workflows/bitcoin_dca.yml` のcron式を編集：

```yaml
schedule:
  - cron: '0 0 28 * *'  # ← ここを変更
```

cron式の例：
- `0 0 28 * *` - 毎月28日 0時（UTC）= 9時（JST）
- `0 0 1 * *` - 毎月1日 0時（UTC）= 9時（JST）
- `0 0 * * *` - 毎日 0時（UTC）= 9時（JST）
- `0 0 * * 1` - 毎週月曜 0時（UTC）= 9時（JST）

注意: GitHubのcron式はUTC基準。日本時間（JST）は+9時間。

## 実行ログの確認

1. リポジトリの「Actions」タブ
2. 実行履歴から確認したい実行をクリック
3. 「buy-btc」ジョブをクリック
4. 各ステップの詳細を確認

## エラー時の対処

**"GMO_API_KEY が環境変数に設定されていません"**
→ GitHub SecretsにAPIキーが正しく設定されているか確認

**"取引エラー"**
→ GMOコインの口座残高、APIキーの取引権限を確認

**"API通信エラー"**
→ GMO APIの一時的な障害の可能性。手動で再実行するか、次回実行まで待つ。

## Lambda版との違い

| | GitHub Actions版 | Lambda版（メイン） |
|---|---|---|
| SNS通知 | なし | あり |
| DRY_RUN | なし | あり |
| 必要なアカウント | GitHub | AWS |
| セットアップ | 簡単 | やや複雑 |

## 更新方法

### GitHubコンソールから
1. フォークしたリポジトリページで「Sync fork」ボタン
2. 「Update branch」をクリック

### コマンドラインから
```bash
# 元のリポジトリをupstreamとして追加（初回のみ）
git remote add upstream https://github.com/Tomoki0612/gmo-btc-dca.git

# 最新を取得
git fetch upstream
git merge upstream/main
git push origin main
```

## 停止方法

**一時停止**: 「Actions」タブ >「Monthly BTC Purchase」>「...」>「Disable workflow」

**完全停止**: リポジトリを削除

## 制限事項

- GitHub Actionsの無料枠: 月2,000分（このワークフローは1回数分なので十分）
- cron式の最短間隔: 5分
- 実行タイミング: GitHub側の負荷状況により数分〜数十分遅れることがある

## セキュリティ

- APIキーは必ずSecretsに保存すること
- フォークしたリポジトリはPrivateにすることを推奨
