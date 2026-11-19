# フロントエンド依存関係の監査

## 2026-11-18の再監査

Create React AppをViteとVitestへ移行し、Node.js 24でビルドします。
`npm audit --package-lock-only --ignore-scripts` のHigh判定は74パッケージから
6パッケージへ減少し、Criticalは0件でした。残る6パッケージはすべて
[picomatchのアドバイザリ](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)に
由来します。確認時点で修正版はなく、対象は開発・ビルド・テスト用の依存です。
Cloudflare Pagesはビルド済みの静的ファイルを配信します。

## 2026-11-16の監査結果

確認日: 2026-11-16。`npm audit --package-lock-only --ignore-scripts --json`で
更新前後のlockfileを比較しました。件数は監査対象のパッケージ数で、独立した脆弱性の件数ではありません。

| 重要度 | 更新前 | 更新後 |
|---|---:|---:|
| Critical | 6 | 0 |
| High | 111 | 13 |
| Moderate | 99 | 5 |
| Low | 144 | 16 |
| 合計 | 360 | 34 |

## 更新と互換性

既存のsemver範囲で依存を更新し、lockfileを保存しました。認証に利用する
`aws-amplify`は6.22.2、`@aws-amplify/ui-react`は6.15.7、`js-cookie`は3.0.8です。
更新前のjs-cookieに対する警告は今回の監査で解消しています。

CRA 5のESLint依存が使うTypeScript APIを維持するため、開発用TypeScriptを
CRAの対応範囲内の4.9.5へ固定しました。Jest 27はRadixの条件付きsubpath exportを
解決できないため、`@radix-ui/primitive/is-development`だけを、同パッケージが
デフォルトで公開する実装へマッピングしています。これはテストだけに適用されます。
本番ビルドのモジュール解決や認証処理を置き換えるものではありません。

Node.js 20でテストとproductionビルドを検証します。`npm audit fix --force`や
`react-scripts@0.0.0`への置換は行っていません。

## 残存警告

更新後の警告は、CRAの開発・ビルド・テスト用依存へつながっています。
このアプリの本番はCloudflare Pages上の静的ファイルで、Node.jsの開発サーバーや
Webpackミドルウェアは公開しません。アプリに利用者がCSS・SVG・コードを投入する機能もありません。
そのため警告の件数だけから、本番ブラウザーでの悪用が可能とは判断しません。
一方、ローカル開発やCIで依存コードが実行されるリスクは残ります。

| 主な依存 | 関係する処理 | 対応方針 |
|---|---|---|
| webpack-dev-server / webpack-dev-middleware | ローカル開発サーバー | 外部へ公開しない。CRA更新・移行時に解消する |
| svgo / nth-check | ビルド時のSVG最適化 | 管理されたリポジトリ内の入力に限定する |
| postcss（resolve-url-loader配下） | ビルド時のCSS・ソースマップ処理 | 未確認のCSSをビルドへ追加しない。互換性のある修正版を追跡する |
| serialize-javascript | ビルド時のシリアライズ | CRA配下の互換性を確認できる更新で解消する |
| underscore / deepmerge / uuid / @tootallnate/once | CRA配下の各ツール | 今回はメジャーバージョンの強制上書きを避ける |

CRAから別のビルドツールへの移行は今回の変更に含めません。
依存の更新時は、監査結果とともにMFA登録・コード入力の統合テスト、既存テスト、
productionビルドを再確認してください。
