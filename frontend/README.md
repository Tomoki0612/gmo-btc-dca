# フロントエンド（Vite）

## Deployment

本番は **Cloudflare Pages** で配信しています。`main` ブランチへの push で自動ビルド・デプロイされます。

### Cloudflare Pages 設定

| 項目 | 値 |
|---|---|
| Framework preset | 任意 |
| Build command | `npm run build` |
| Build output directory | `build` |
| Root directory | `frontend` |
| Node.js | `.node-version` で指定 |

Pagesに `NODE_VERSION=20` を設定している場合は、変数を削除して `.node-version` を使うか、
同ファイルと同じバージョンに更新してください。

バックエンド接続先には次の環境変数がすべて必須です。本番への誤接続を防ぐため、
1つでも未設定なら`npm start`と`npm run build`は失敗します。

| 環境変数 | SAM Output |
|---|---|
| `REACT_APP_API_BASE_URL` | `ApiBaseUrl` |
| `REACT_APP_COGNITO_USER_POOL_ID` | `UserPoolId` |
| `REACT_APP_COGNITO_USER_POOL_CLIENT_ID` | `UserPoolClientId` |

ローカル設定例は `.env.example` を参照してください。

API側のSAMパラメータ`FrontendOrigin`にも、ここでデプロイするフロントURLを末尾の
スラッシュなしで設定してください。

### API認証

ログイン後、`fetchAuthSession()` で取得したCognito IDトークンを、バックエンドAPIの
`Authorization` ヘッダーへ設定する。外部API（mempool.space）にはトークンを送信しない。

API Gateway、Cognito Authorizer、CORS、Lambda実行権限はすべて
`aws-lambda/template.yaml` で管理します。個別のAWS CLI設定は不要です。

### 二段階認証

CognitoでTOTPを必須にし、既存のAuthenticatorが初回のQR登録と次回以降のコード入力を扱います。
無料の単体アプリBitwarden AuthenticatorでQRコードを登録してください。発行元は「ツミビット」です。
コードが拒否された場合は端末の時刻を自動設定にし、新しい6桁コードで再試行します。
SMSは使いません。QR生成のための外部サービスも追加しません。
本番への適用順序と端末紛失時の手順は[バックエンドの説明](../aws-lambda/README.md#bitwarden-authenticatorでの二段階認証)を参照してください。

## ローカル開発

- `npm ci` でロックファイルどおりに依存をインストールします。
- `npm start` で開発サーバーを起動します。既定は `http://localhost:3000` です。
- `npm test` でユニットテストを実行します。
- `npm run build` で本番ファイルを `build` に生成します。
- `npm audit --package-lock-only --ignore-scripts` で依存関係を監査します。
