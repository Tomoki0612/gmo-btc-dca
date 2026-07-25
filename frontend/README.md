# Frontend (Create React App)

This project was bootstrapped with [Create React App](https://github.com/facebook/create-react-app).

## Deployment

本番は **Cloudflare Pages** で配信しています。`main` ブランチへの push で自動ビルド・デプロイされます。

### Cloudflare Pages 設定

| 項目 | 値 |
|---|---|
| Framework preset | Create React App |
| Build command | `npm run build` |
| Build output directory | `build` |
| Root directory | `frontend` |
| Node version (環境変数 `NODE_VERSION`) | `20` |

バックエンド接続先は次の環境変数で上書きできます。未設定時は本番SAMスタックの
Outputsに対応する既定値を使用します。

| 環境変数 | SAM Output |
|---|---|
| `REACT_APP_API_BASE_URL` | `ApiBaseUrl` |
| `REACT_APP_COGNITO_USER_POOL_ID` | `UserPoolId` |
| `REACT_APP_COGNITO_USER_POOL_CLIENT_ID` | `UserPoolClientId` |

ローカル設定例は `.env.example` を参照してください。

### API認証

ログイン後、`fetchAuthSession()` で取得したCognito IDトークンを、バックエンドAPIの
`Authorization` ヘッダーへ設定する。外部API（mempool.space）にはトークンを送信しない。

API Gateway、Cognito Authorizer、CORS、Lambda実行権限はすべて
`aws-lambda/template.yaml` で管理します。個別のAWS CLI設定は不要です。

## Available Scripts

In the project directory, you can run:

### `npm start`

Runs the app in the development mode.\
Open [http://localhost:3000](http://localhost:3000) to view it in your browser.

The page will reload when you make changes.\
You may also see any lint errors in the console.

### `npm test`

Launches the test runner in the interactive watch mode.\
See the section about [running tests](https://facebook.github.io/create-react-app/docs/running-tests) for more information.

### `npm run build`

Builds the app for production to the `build` folder.\
It correctly bundles React in production mode and optimizes the build for the best performance.

The build is minified and the filenames include the hashes.\
Your app is ready to be deployed!

See the section about [deployment](https://facebook.github.io/create-react-app/docs/deployment) for more information.

### `npm run eject`

**Note: this is a one-way operation. Once you `eject`, you can't go back!**

If you aren't satisfied with the build tool and configuration choices, you can `eject` at any time. This command will remove the single build dependency from your project.

Instead, it will copy all the configuration files and the transitive dependencies (webpack, Babel, ESLint, etc) right into your project so you have full control over them. All of the commands except `eject` will still work, but they will point to the copied scripts so you can tweak them. At this point you're on your own.

You don't have to ever use `eject`. The curated feature set is suitable for small and middle deployments, and you shouldn't feel obligated to use this feature. However we understand that this tool wouldn't be useful if you couldn't customize it when you are ready for it.

## Learn More

You can learn more in the [Create React App documentation](https://facebook.github.io/create-react-app/docs/getting-started).

To learn React, check out the [React documentation](https://reactjs.org/).

### Code Splitting

This section has moved here: [https://facebook.github.io/create-react-app/docs/code-splitting](https://facebook.github.io/create-react-app/docs/code-splitting)

### Analyzing the Bundle Size

This section has moved here: [https://facebook.github.io/create-react-app/docs/analyzing-the-bundle-size](https://facebook.github.io/create-react-app/docs/analyzing-the-bundle-size)

### Making a Progressive Web App

This section has moved here: [https://facebook.github.io/create-react-app/docs/making-a-progressive-web-app](https://facebook.github.io/create-react-app/docs/making-a-progressive-web-app)

### Advanced Configuration

This section has moved here: [https://facebook.github.io/create-react-app/docs/advanced-configuration](https://facebook.github.io/create-react-app/docs/advanced-configuration)

### Deployment

This section has moved here: [https://facebook.github.io/create-react-app/docs/deployment](https://facebook.github.io/create-react-app/docs/deployment)

### `npm run build` fails to minify

This section has moved here: [https://facebook.github.io/create-react-app/docs/troubleshooting#npm-run-build-fails-to-minify](https://facebook.github.io/create-react-app/docs/troubleshooting#npm-run-build-fails-to-minify)
