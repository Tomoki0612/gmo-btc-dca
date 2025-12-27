# GitHub Actions セットアップ手順

GitHub Actionsを使って、毎日自動でBTCを積立購入します。

## ✨ メリット

- 完全無料
- セットアップが簡単（5分で完了）
- GitHubアカウントだけで動作
- サーバー不要

## 📋 前提条件

1. GitHubアカウント
2. GMOコインのアカウント
3. GMOコインのAPIキー・シークレットキー

## 🚀 セットアップ手順

### 1. このリポジトリをフォーク

右上の「Fork」ボタンをクリックして、自分のアカウントにコピー

### 2. GitHub Secretsを設定

1. フォークしたリポジトリに移動
2. 「Settings」タブをクリック
3. 左メニューから「Secrets and variables」>「Actions」を選択
4. 「New repository secret」をクリック

以下の2つのSecretを追加：

**Secret 1: GMO_API_KEY**
- Name: `GMO_API_KEY`
- Secret: あなたのGMO APIキー

**Secret 2: GMO_API_SECRET**
- Name: `GMO_API_SECRET`
- Secret: あなたのGMOシークレットキー

### 3. GitHub Actionsを有効化

1. 「Actions」タブをクリック
2. 「I understand my workflows, go ahead and enable them」をクリック

### 4. 初回実行（テスト）

1. 「Actions」タブで「BTC Daily Purchase」をクリック
2. 「Run workflow」をクリック
3. 「Run workflow」ボタンを再度クリック

数分待って実行結果を確認。緑のチェックマークが出れば成功！

## ⚙️ 設定のカスタマイズ

### 積立金額を変更

`github-actions/btc_purchase.py` を編集：

```python
# この部分を変更
INVESTMENT_AMOUNT = 10000  # 10,000円 → 好きな金額に
```

変更後、コミット＆プッシュすれば次回から反映されます。

### 実行時刻を変更

`.github/workflows/btc-buy.yml` のcron式を編集：

```yaml
schedule:
  - cron: '0 0 * * *'  # ← ここを変更
```

**cron式の例：**
- `0 0 * * *` - 毎日0時（UTC）= 毎日9時（JST）
- `0 1 * * *` - 毎日1時（UTC）= 毎日10時（JST）
- `0 */12 * * *` - 12時間ごと
- `0 0 * * 1` - 毎週月曜日0時（UTC）

⚠️ **注意**: GitHubのcron式はUTC基準です。日本時間（JST）は+9時間なので注意してください。

## 📊 実行ログの確認

1. リポジトリの「Actions」タブ
2. 実行履歴から確認したい実行をクリック
3. 「buy-btc」ジョブをクリック
4. 各ステップの詳細を確認

### 成功時のログ例
```
積立開始: 2024-01-15T00:00:00
積立金額: ¥10,000
BTC価格: ¥6,500,000
購入数量: 0.00154 BTC
取引が正常に完了しました
```

### エラー時の対処

**エラー: "GMO_API_KEY が環境変数に設定されていません"**
→ GitHub SecretsにAPIキーが正しく設定されているか確認

**エラー: "取引エラー"**
→ GMOコインの口座に十分な残高があるか確認
→ APIキーに取引権限があるか確認

**エラー: "API通信エラー"**
→ GMO APIが一時的にダウンしている可能性
→ 次回実行時に自動的にリトライされます

## 🔄 更新方法

このリポジトリが更新された場合：

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

## 🛑 停止方法

### 一時停止
1. 「Actions」タブ
2. 左メニューの「BTC Daily Purchase」
3. 「...」メニュー >「Disable workflow」

### 完全停止
リポジトリを削除

## 💡 Tips

### 手動実行
定期実行を待たずにテストしたい場合：
1. 「Actions」タブ >「BTC Daily Purchase」
2. 「Run workflow」で即座に実行

### 実行を一時的にスキップ
コミットメッセージに `[skip ci]` を含めると、そのコミットではワークフローが実行されません。

### 複数の積立設定
- ワークフローファイルを複製して別の時間に実行
- 別の通貨（ETH等）にも対応可能

## ⚠️ 制限事項

- GitHub Actionsの無料枠：月2,000分まで（このワークフローは1回数分なので問題なし）
- 最短実行間隔：5分（cron式の制限）
- 実行タイミング：負荷が高い時は数分遅れることがある

## 🔐 セキュリティ

- APIキーは必ずSecretsに保存
- ログにAPIキーが表示されないように注意
- フォークしたリポジトリはPrivateにすることを推奨

## ❓ FAQ

**Q: 土日も実行されますか？**
A: はい。ただし市場が閉まっている時間は約定しません。

**Q: 失敗した場合は自動でリトライされますか？**
A: いいえ。次の実行時間まで待つか、手動で再実行してください。

**Q: 購入履歴はどこで確認できますか？**
A: GMOコインの取引履歴で確認できます。

**Q: 複数の通貨を積立できますか？**
A: コードを修正すれば可能です。`symbol`を変更してください。

## 📞 サポート

問題が発生した場合は、GitHubのIssuesで報告してください。