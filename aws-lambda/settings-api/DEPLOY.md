# settings-api デプロイ手順 (AWS CLI)

`/balance` `/history` エンドポイント追加作業。`deploy.sh` を叩くだけで完了するように冪等化済み。

---

## 前提

- AWS CLI v2 がインストール済み (`aws --version`)
- `aws configure` 済み、または `AWS_PROFILE` が設定済み
- 実行ユーザーに以下の IAM 権限があること:
  - `lambda:UpdateFunctionCode` / `UpdateFunctionConfiguration` / `GetFunction` / `AddPermission`
  - `apigateway:*`（対象 REST API のリソース作成・デプロイ）
  - `sts:GetCallerIdentity`
- （疎通確認に使うなら）`jq` と `curl`

前提リソース（既存のまま利用）:
- Lambda 関数名: `settings-api`
- REST API ID: `5slu1ftn2g`
- ステージ: `prod`
- リージョン: `ap-northeast-1`

---

## 0. 前準備 — `btc-dca-history` テーブル

履歴用 DynamoDB テーブルが必要。未作成なら下記で作成（auto-purchase 側の SAM でも同テーブルを作成するので、どちらか片方で十分）。

```bash
aws dynamodb create-table \
  --region ap-northeast-1 \
  --table-name btc-dca-history \
  --attribute-definitions AttributeName=userId,AttributeType=S AttributeName=sk,AttributeType=S \
  --key-schema AttributeName=userId,KeyType=HASH AttributeName=sk,KeyType=RANGE \
  --billing-mode PAY_PER_REQUEST
```

Lambda 実行ロール（`settings-api` 関数）に以下の権限を追加すること:

```json
{
  "Effect": "Allow",
  "Action": ["dynamodb:Query", "dynamodb:PutItem"],
  "Resource": "arn:aws:dynamodb:ap-northeast-1:<ACCOUNT_ID>:table/btc-dca-history"
}
```

---

## 1. 実行

```bash
cd aws-lambda/settings-api
./deploy.sh
```

スクリプトがやること:

1. `lambda_function.py` を zip にしてアップロード
2. Lambda のタイムアウトを 15s に
3. API Gateway ルートリソース ID を取得
4. `/balance` リソースを作成（既存なら再利用）
5. Lambda ARN とアカウント ID を取得
6. `GET /balance` → Lambda プロキシ統合
7. API Gateway → Lambda の呼び出し権限を付与
8. `OPTIONS /balance` → CORS 用 MOCK 統合（Allow-Origin: `*`, Methods: `GET,OPTIONS`）
9. `prod` ステージへデプロイ

再実行しても既存リソースは壊しません（`put-method`/`add-permission` は衝突をスキップ）。

---

## 2. 疎通確認

```bash
curl -s https://5slu1ftn2g.execute-api.ap-northeast-1.amazonaws.com/prod/balance | jq .
```

期待レスポンス:

- APIキー設定済み:
  ```json
  {
    "configured": true,
    "jpy": 48018.0,
    "btc": 0.00094,
    "btcJpyRate": 12391000.0,
    "updatedAt": "2026-04-23T11:26:35.335659Z"
  }
  ```
- APIキー未設定: `{"configured": false}`

CORS プリフライト確認:

```bash
curl -i -X OPTIONS \
  -H 'Origin: https://<your-project>.pages.dev' \
  -H 'Access-Control-Request-Method: GET' \
  https://5slu1ftn2g.execute-api.ap-northeast-1.amazonaws.com/prod/balance
```

`Access-Control-Allow-Origin: *` が返ればOK。

---

## 3. フロント反映

`main` ブランチに push すれば Cloudflare Pages が自動でビルド・デプロイします（プロジェクト URL は `*.pages.dev`）。

---

## 4. ロールバック

### Lambda コードのみ戻す

```bash
# 以前発行したバージョンに戻す場合 (事前に publish が必要)
aws lambda update-alias \
  --region ap-northeast-1 \
  --function-name settings-api \
  --name prod \
  --function-version <revert-target-version>
```

バージョン管理していない場合は、旧 `lambda_function.py` を手元に戻して再度 `./deploy.sh`。

### /balance ルートを丸ごと削除

```bash
REGION=ap-northeast-1
REST_API_ID=5slu1ftn2g
BALANCE_ID=$(aws apigateway get-resources --region $REGION --rest-api-id $REST_API_ID \
  --query "items[?path=='/balance'].id" --output text)
aws apigateway delete-resource --region $REGION --rest-api-id $REST_API_ID --resource-id "$BALANCE_ID"
aws apigateway create-deployment --region $REGION --rest-api-id $REST_API_ID --stage-name prod
```

---

## 5. よくあるハマり

| 症状 | 原因 | 対処 |
|---|---|---|
| `{"message":"Missing Authentication Token"}` | `prod` ステージへの再デプロイ漏れ（CLI がデプロイ失敗） | `aws apigateway create-deployment ... --stage-name prod` を手動実行 |
| CORS エラー | 9 の OPTIONS 統合が失敗 | `deploy.sh` を再実行。integration-response のメソッド定義順序に注意 |
| `502 GMOコインAPIエラー (401)` | APIキー/シークレット誤り or 権限不足 | GMOコイン側で取引権限付きキーを再発行して画面で保存 |
| `Task timed out after X seconds` | Lambda タイムアウト | `TIMEOUT_SEC` を上げて再実行 |
| `AccessDenied: not authorized` | CLI のユーザーに権限不足 | 上記「前提」の IAM 権限を付与 |
