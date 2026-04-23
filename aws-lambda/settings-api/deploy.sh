#!/usr/bin/env bash
# settings-api Lambda のコード更新 + API Gateway /balance ルート作成 を AWS CLI で実行。
# 冪等なので再実行しても既存リソースを壊さない (存在チェック付き)。

set -euo pipefail

REGION=ap-northeast-1
REST_API_ID=5slu1ftn2g
STAGE=prod
TIMEOUT_SEC=15
# 関数名は環境変数で明示指定できる。未指定なら /settings 統合から自動取得。
FUNCTION_NAME="${FUNCTION_NAME:-}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ZIP_PATH="$(mktemp -t settings-api-XXXXXX.zip)"
rm -f "$ZIP_PATH"  # zip は空ファイルを壊れた zip として読むため事前削除
trap 'rm -f "$ZIP_PATH"' EXIT

echo "==> 0. 既存 /settings 統合から Lambda 関数名を自動取得"
SETTINGS_ID=$(aws apigateway get-resources --region "$REGION" --rest-api-id "$REST_API_ID" \
  --query "items[?path=='/settings'].id" --output text)
if [ -z "$SETTINGS_ID" ] || [ "$SETTINGS_ID" = "None" ]; then
  echo "    /settings リソースが見つかりません。REST_API_ID を確認してください" >&2
  exit 1
fi
SETTINGS_URI=$(aws apigateway get-integration \
  --region "$REGION" --rest-api-id "$REST_API_ID" \
  --resource-id "$SETTINGS_ID" --http-method GET \
  --query uri --output text)
DISCOVERED_NAME=$(echo "$SETTINGS_URI" | sed -n 's|.*:function:\([^/]*\)/invocations|\1|p')
if [ -z "$FUNCTION_NAME" ]; then
  FUNCTION_NAME="$DISCOVERED_NAME"
fi
if [ -z "$FUNCTION_NAME" ]; then
  echo "    関数名が解決できません。FUNCTION_NAME=xxxxx ./deploy.sh で明示指定してください" >&2
  exit 1
fi
echo "    Lambda function: $FUNCTION_NAME"

echo "==> 1. Lambda コードをパッケージ化"
(cd "$SCRIPT_DIR" && zip -q -j "$ZIP_PATH" lambda_function.py)

echo "==> 2. Lambda コードを更新"
aws lambda update-function-code \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://$ZIP_PATH" \
  >/dev/null
aws lambda wait function-updated \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME"

echo "==> 3. タイムアウトを ${TIMEOUT_SEC}s に設定"
aws lambda update-function-configuration \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --timeout "$TIMEOUT_SEC" \
  >/dev/null

echo "==> 4. ルートリソース ID を取得"
ROOT_ID=$(aws apigateway get-resources \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --query "items[?path=='/'].id" --output text)
echo "    root: $ROOT_ID"

echo "==> 5. /balance リソースを取得または作成"
BALANCE_ID=$(aws apigateway get-resources \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --query "items[?path=='/balance'].id" --output text)
if [ -z "$BALANCE_ID" ] || [ "$BALANCE_ID" = "None" ]; then
  BALANCE_ID=$(aws apigateway create-resource \
    --region "$REGION" \
    --rest-api-id "$REST_API_ID" \
    --parent-id "$ROOT_ID" \
    --path-part balance \
    --query id --output text)
  echo "    created: $BALANCE_ID"
else
  echo "    exists: $BALANCE_ID"
fi

echo "==> 6. Lambda ARN とアカウント ID を取得"
LAMBDA_ARN=$(aws lambda get-function \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --query Configuration.FunctionArn --output text)
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
INTEGRATION_URI="arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$LAMBDA_ARN/invocations"

echo "==> 7. GET /balance メソッドと Lambda プロキシ統合"
aws apigateway put-method \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$BALANCE_ID" \
  --http-method GET \
  --authorization-type NONE \
  >/dev/null 2>&1 || echo "    GET method already exists"

aws apigateway put-integration \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$BALANCE_ID" \
  --http-method GET \
  --type AWS_PROXY \
  --integration-http-method POST \
  --uri "$INTEGRATION_URI" \
  >/dev/null

echo "==> 8. Lambda に API Gateway からの実行権限を付与"
aws lambda add-permission \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --statement-id apigw-balance-get \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT_ID:$REST_API_ID/*/GET/balance" \
  >/dev/null 2>&1 || echo "    permission already exists"

echo "==> 9. OPTIONS メソッド (CORS 用 MOCK 統合)"
aws apigateway put-method \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$BALANCE_ID" \
  --http-method OPTIONS \
  --authorization-type NONE \
  >/dev/null 2>&1 || echo "    OPTIONS method already exists"

aws apigateway put-method-response \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$BALANCE_ID" \
  --http-method OPTIONS \
  --status-code 200 \
  --response-parameters "$(cat <<'JSON'
{
  "method.response.header.Access-Control-Allow-Origin": true,
  "method.response.header.Access-Control-Allow-Headers": true,
  "method.response.header.Access-Control-Allow-Methods": true
}
JSON
)" \
  >/dev/null 2>&1 || echo "    OPTIONS method response already exists"

aws apigateway put-integration \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$BALANCE_ID" \
  --http-method OPTIONS \
  --type MOCK \
  --request-templates '{"application/json":"{\"statusCode\":200}"}' \
  >/dev/null

aws apigateway put-integration-response \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$BALANCE_ID" \
  --http-method OPTIONS \
  --status-code 200 \
  --response-parameters "$(cat <<'JSON'
{
  "method.response.header.Access-Control-Allow-Origin": "'*'",
  "method.response.header.Access-Control-Allow-Headers": "'Content-Type'",
  "method.response.header.Access-Control-Allow-Methods": "'GET,OPTIONS'"
}
JSON
)" \
  >/dev/null

echo "==> 10. ${STAGE} ステージへデプロイ"
aws apigateway create-deployment \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --stage-name "$STAGE" \
  --description "add /balance endpoint" \
  >/dev/null

echo ""
echo "✅ Done."
echo ""
echo "疎通確認:"
echo "  curl -s https://$REST_API_ID.execute-api.$REGION.amazonaws.com/$STAGE/balance | jq ."
echo ""
echo "CORS 確認:"
echo "  curl -i -X OPTIONS \\"
echo "    -H 'Origin: https://main.d3jt59ecaltvq1.amplifyapp.com' \\"
echo "    -H 'Access-Control-Request-Method: GET' \\"
echo "    https://$REST_API_ID.execute-api.$REGION.amazonaws.com/$STAGE/balance"
