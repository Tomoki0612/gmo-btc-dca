#!/usr/bin/env bash
# settings-api Lambda のコード更新 + API Gateway /balance ルート作成 を AWS CLI で実行。
# 冪等なので再実行しても既存リソースを壊さない (存在チェック付き)。

set -euo pipefail

REGION=ap-northeast-1
REST_API_ID=5slu1ftn2g
STAGE=prod
TIMEOUT_SEC=15
SSM_PARAMETER_NAME="/gmo-btc-dca/prod/gmo-api-credentials"
USER_POOL_ID="${USER_POOL_ID:-ap-northeast-1_4R5AGWXtg}"
API_AUTH_MODE="${API_AUTH_MODE:-enforce}"
AUTHORIZER_NAME=btc-dca-cognito
# 関数名は環境変数で明示指定できる。未指定なら /settings 統合から自動取得。
FUNCTION_NAME="${FUNCTION_NAME:-}"

if [ "$API_AUTH_MODE" != "cors-only" ] && [ "$API_AUTH_MODE" != "enforce" ]; then
  echo "API_AUTH_MODE は cors-only または enforce を指定してください" >&2
  exit 1
fi

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

echo "==> 1. Cognito Authorizerを取得または作成"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
USER_POOL_ARN="arn:aws:cognito-idp:$REGION:$ACCOUNT_ID:userpool/$USER_POOL_ID"
AUTHORIZER_ID=$(aws apigateway get-authorizers \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --query "items[?name=='$AUTHORIZER_NAME'].id" --output text)
if [ -z "$AUTHORIZER_ID" ] || [ "$AUTHORIZER_ID" = "None" ]; then
  AUTHORIZER_ID=$(aws apigateway create-authorizer \
    --region "$REGION" \
    --rest-api-id "$REST_API_ID" \
    --name "$AUTHORIZER_NAME" \
    --type COGNITO_USER_POOLS \
    --provider-arns "$USER_POOL_ARN" \
    --identity-source method.request.header.Authorization \
    --query id --output text)
  echo "    created: $AUTHORIZER_ID"
else
  CURRENT_USER_POOL_ARN=$(aws apigateway get-authorizer \
    --region "$REGION" \
    --rest-api-id "$REST_API_ID" \
    --authorizer-id "$AUTHORIZER_ID" \
    --query 'providerARNs[0]' --output text)
  if [ "$CURRENT_USER_POOL_ARN" != "$USER_POOL_ARN" ]; then
    echo "既存AuthorizerのUser Poolが一致しません: $CURRENT_USER_POOL_ARN" >&2
    exit 1
  fi
  echo "    exists: $AUTHORIZER_ID"
fi

protect_method() {
  local resource_id="$1"
  local http_method="$2"
  if [ "$API_AUTH_MODE" = "enforce" ]; then
    aws apigateway update-method \
      --region "$REGION" \
      --rest-api-id "$REST_API_ID" \
      --resource-id "$resource_id" \
      --http-method "$http_method" \
      --patch-operations \
        "op=replace,path=/authorizationType,value=COGNITO_USER_POOLS" \
        "op=replace,path=/authorizerId,value=$AUTHORIZER_ID" \
      >/dev/null
  fi
}

echo "==> 2. Lambda 実行ロールにSSM SecureStringの読み書き権限を設定"
LAMBDA_ROLE_ARN=$(aws lambda get-function \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --query Configuration.Role --output text)
ROLE_NAME="${LAMBDA_ROLE_ARN##*/}"
aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name btc-dca-ssm-credentials \
  --policy-document "$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ssm:GetParameter", "ssm:PutParameter"],
      "Resource": "arn:aws:ssm:$REGION:$ACCOUNT_ID:parameter${SSM_PARAMETER_NAME}"
    }
  ]
}
JSON
)"

echo "==> 3. Lambda コードをパッケージ化"
(cd "$SCRIPT_DIR" && zip -q -j "$ZIP_PATH" lambda_function.py)

echo "==> 4. Lambda コードを更新"
aws lambda update-function-code \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --zip-file "fileb://$ZIP_PATH" \
  >/dev/null
aws lambda wait function-updated \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME"

echo "==> 5. タイムアウトを ${TIMEOUT_SEC}s に設定"
aws lambda update-function-configuration \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --timeout "$TIMEOUT_SEC" \
  >/dev/null

echo "==> 6. ルートリソース ID を取得"
ROOT_ID=$(aws apigateway get-resources \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --query "items[?path=='/'].id" --output text)
echo "    root: $ROOT_ID"

echo "==> 7. /balance リソースを取得または作成"
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

echo "==> 8. Lambda ARNを取得"
LAMBDA_ARN=$(aws lambda get-function \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --query Configuration.FunctionArn --output text)
INTEGRATION_URI="arn:aws:apigateway:$REGION:lambda:path/2015-03-31/functions/$LAMBDA_ARN/invocations"

echo "==> 9. GET /balance メソッドと Lambda プロキシ統合"
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

echo "==> 10. Lambda に API Gateway からの実行権限を付与"
aws lambda add-permission \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --statement-id apigw-balance-get \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT_ID:$REST_API_ID/*/GET/balance" \
  >/dev/null 2>&1 || echo "    permission already exists"

echo "==> 11. OPTIONS メソッド (CORS 用 MOCK 統合)"
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
  "method.response.header.Access-Control-Allow-Headers": "'Content-Type,Authorization'",
  "method.response.header.Access-Control-Allow-Methods": "'GET,OPTIONS'"
}
JSON
)" \
  >/dev/null

echo "==> 12. /history リソースを取得または作成"
HISTORY_ID=$(aws apigateway get-resources \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --query "items[?path=='/history'].id" --output text)
if [ -z "$HISTORY_ID" ] || [ "$HISTORY_ID" = "None" ]; then
  HISTORY_ID=$(aws apigateway create-resource \
    --region "$REGION" \
    --rest-api-id "$REST_API_ID" \
    --parent-id "$ROOT_ID" \
    --path-part history \
    --query id --output text)
  echo "    created: $HISTORY_ID"
else
  echo "    exists: $HISTORY_ID"
fi

aws apigateway put-method \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$HISTORY_ID" \
  --http-method GET \
  --authorization-type NONE \
  >/dev/null 2>&1 || echo "    GET /history method already exists"

aws apigateway put-integration \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$HISTORY_ID" \
  --http-method GET \
  --type AWS_PROXY \
  --integration-http-method POST \
  --uri "$INTEGRATION_URI" \
  >/dev/null

aws lambda add-permission \
  --region "$REGION" \
  --function-name "$FUNCTION_NAME" \
  --statement-id apigw-history-get \
  --action lambda:InvokeFunction \
  --principal apigateway.amazonaws.com \
  --source-arn "arn:aws:execute-api:$REGION:$ACCOUNT_ID:$REST_API_ID/*/GET/history" \
  >/dev/null 2>&1 || echo "    /history permission already exists"

aws apigateway put-method \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$HISTORY_ID" \
  --http-method OPTIONS \
  --authorization-type NONE \
  >/dev/null 2>&1 || echo "    OPTIONS /history method already exists"

aws apigateway put-method-response \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$HISTORY_ID" \
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
  >/dev/null 2>&1 || echo "    OPTIONS /history method response already exists"

aws apigateway put-integration \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$HISTORY_ID" \
  --http-method OPTIONS \
  --type MOCK \
  --request-templates '{"application/json":"{\"statusCode\":200}"}' \
  >/dev/null

aws apigateway put-integration-response \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$HISTORY_ID" \
  --http-method OPTIONS \
  --status-code 200 \
  --response-parameters "$(cat <<'JSON'
{
  "method.response.header.Access-Control-Allow-Origin": "'*'",
  "method.response.header.Access-Control-Allow-Headers": "'Content-Type,Authorization'",
  "method.response.header.Access-Control-Allow-Methods": "'GET,OPTIONS'"
}
JSON
)" \
  >/dev/null

echo "==> 13. /settings のCORSをAuthorizationヘッダー対応に更新"
aws apigateway put-method \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$SETTINGS_ID" \
  --http-method OPTIONS \
  --authorization-type NONE \
  >/dev/null 2>&1 || echo "    OPTIONS /settings method already exists"

aws apigateway put-method-response \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$SETTINGS_ID" \
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
  >/dev/null 2>&1 || echo "    OPTIONS /settings method response already exists"

aws apigateway put-integration \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$SETTINGS_ID" \
  --http-method OPTIONS \
  --type MOCK \
  --request-templates '{"application/json":"{\"statusCode\":200}"}' \
  >/dev/null

aws apigateway put-integration-response \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --resource-id "$SETTINGS_ID" \
  --http-method OPTIONS \
  --status-code 200 \
  --response-parameters "$(cat <<'JSON'
{
  "method.response.header.Access-Control-Allow-Origin": "'*'",
  "method.response.header.Access-Control-Allow-Headers": "'Content-Type,Authorization'",
  "method.response.header.Access-Control-Allow-Methods": "'GET,POST,OPTIONS'"
}
JSON
)" \
  >/dev/null

echo "==> 14. APIメソッドのCognito認証を設定 (mode: $API_AUTH_MODE)"
protect_method "$SETTINGS_ID" GET
protect_method "$SETTINGS_ID" POST
protect_method "$BALANCE_ID" GET
protect_method "$HISTORY_ID" GET

echo "==> 15. 認証エラー応答にCORSヘッダーを設定"
for response_type in UNAUTHORIZED ACCESS_DENIED; do
  aws apigateway put-gateway-response \
    --region "$REGION" \
    --rest-api-id "$REST_API_ID" \
    --response-type "$response_type" \
    --response-parameters "$(cat <<'JSON'
{
  "gatewayresponse.header.Access-Control-Allow-Origin": "'*'",
  "gatewayresponse.header.Access-Control-Allow-Headers": "'Content-Type,Authorization'"
}
JSON
)" \
    >/dev/null
done

echo "==> 16. ${STAGE} ステージへデプロイ"
aws apigateway create-deployment \
  --region "$REGION" \
  --rest-api-id "$REST_API_ID" \
  --stage-name "$STAGE" \
  --description "secure settings APIs with Cognito ($API_AUTH_MODE)" \
  >/dev/null

echo ""
echo "✅ Done."
echo ""
if [ "$API_AUTH_MODE" = "cors-only" ]; then
  echo "CORSのみ更新しました。JWT対応フロントを公開後、API_AUTH_MODE=enforce で再実行してください。"
else
  echo "Cognito認証を有効化しました。AuthorizationヘッダーなしのAPI呼び出しは拒否されます。"
fi
echo ""
echo "疎通確認:"
echo "  curl -H 'Authorization: <Cognito ID token>' \\"
echo "    https://$REST_API_ID.execute-api.$REGION.amazonaws.com/$STAGE/balance | jq ."
echo ""
echo "CORS 確認:"
echo "  curl -i -X OPTIONS \\"
echo "    -H 'Origin: https://main.d3jt59ecaltvq1.amplifyapp.com' \\"
echo "    -H 'Access-Control-Request-Method: GET' \\"
echo "    https://$REST_API_ID.execute-api.$REGION.amazonaws.com/$STAGE/balance"
