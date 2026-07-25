# settings-api デプロイ手順 (AWS CLI)

`/balance` `/history` エンドポイント追加作業。`deploy.sh` を叩くだけで完了するように冪等化済み。

---

## 前提

- AWS CLI v2 がインストール済み (`aws --version`)
- `aws configure` 済み、または `AWS_PROFILE` が設定済み
- 実行ユーザーに以下の IAM 権限があること:
  - `lambda:UpdateFunctionCode` / `UpdateFunctionConfiguration` / `GetFunction` / `AddPermission`
  - `apigateway:*`（対象 REST API のリソース作成・デプロイ）
  - `iam:PutRolePolicy`（LambdaにParameter Store権限を設定）
  - `sts:GetCallerIdentity`
- （疎通確認に使うなら）`jq` と `curl`

前提リソース（既存のまま利用）:
- Lambda 関数名: `settings-api`
- REST API ID: `5slu1ftn2g`
- ステージ: `prod`
- リージョン: `ap-northeast-1`

---

## 0. 前準備 — `btc-dca-history` テーブル

履歴用 DynamoDB テーブルが必要。現在の本番テーブルは既存データを保持するため、
auto-purchase側のSAMスタックには含めず、既存リソースとして参照する。
未作成の環境では下記で作成する。

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

CORSとJWT対応フロントを先に反映してから認証を必須化する。初回は次の順序で実行する。

```bash
# 1. AuthorizationヘッダーをCORSで許可（APIはまだ認証必須にしない）
cd aws-lambda/settings-api
API_AUTH_MODE=cors-only ./deploy.sh

# 2. JWT対応フロントをCloudflare Pagesへデプロイ
# mainへのpush、またはCloudflare側で再デプロイ

# 3. Cognito認証を必須化
API_AUTH_MODE=enforce ./deploy.sh
```

すでにJWT対応フロントが公開済みなら、以降は通常どおり `./deploy.sh` だけでよい。
`USER_POOL_ID` を省略した場合は `ap-northeast-1_4R5AGWXtg` を使用する。

スクリプトがやること:

1. 既存Cognito User Poolを使うAPI Gateway Authorizerを作成・更新
2. Lambda実行ロールにSSM Parameter Storeの読み書き権限を設定
3. `lambda_function.py` をzipにしてアップロード
4. `/settings` `/balance` `/history` のCORSを設定
5. `enforce` モードではGET/POSTにCognito認証を設定
6. `prod` ステージへデプロイ

GMO APIキーとシークレットは、Standard TierのSecureString
`/gmo-btc-dca/prod/gmo-api-credentials` にJSONとして保存される。
設定APIのGETレスポンスには認証情報そのものを含めず、`apiConfigured` のみ返す。

旧バージョンでDynamoDBの `apiKey` / `apiSecret` に保存された値は、次回の設定POST時に
SecureStringへ自動移行され、DynamoDBから削除される。それまでは自動購入Lambdaが旧値へ
フォールバックする。

再実行しても既存リソースは壊しません（`put-method`/`add-permission` は衝突をスキップ）。

---

## 2. 疎通確認

```bash
curl -s \
  -H "Authorization: <Cognito ID token>" \
  https://5slu1ftn2g.execute-api.ap-northeast-1.amazonaws.com/prod/balance | jq .
```

Authorizationヘッダーなしのリクエストが `401 Unauthorized` になることも確認する。

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
  -H 'Access-Control-Request-Headers: Authorization' \
  https://5slu1ftn2g.execute-api.ap-northeast-1.amazonaws.com/prod/balance
```

`Access-Control-Allow-Origin: *` と `Access-Control-Allow-Headers: Content-Type,Authorization`
が返ればOK。

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
