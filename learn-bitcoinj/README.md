# bitcoinjでJavaを学ぶ

bitcoinjライブラリを使いながらJavaの基本を学ぶプロジェクトです。

## 必要なもの

- Java 17以上
- Gradle（Gradle Wrapperを同梱）

## レッスン一覧

| レッスン | テーマ | 学べるJavaの概念 |
|---------|--------|-----------------|
| Lesson1 | 鍵ペアとアドレス | クラス, メソッド呼び出し, 文字列操作, for文 |
| Lesson2 | ウォレット作成 | List, null チェック, printf, 配列操作 |
| Lesson3 | トランザクション | 例外処理, オブジェクトの関連, enum |

## 実行方法

```bash
cd learn-bitcoinj

# レッスン1: Bitcoinの基本（鍵、アドレス、単位）
./gradlew runLesson1

# レッスン2: ウォレットの作成と管理
./gradlew runLesson2

# レッスン3: トランザクションの仕組み
./gradlew runLesson3
```

## プロジェクト構成

```
learn-bitcoinj/
├── build.gradle          # 依存関係とビルド設定
├── settings.gradle
└── src/main/java/com/example/bitcoinj/
    ├── Lesson1.java      # 鍵ペアとアドレス
    ├── Lesson2.java      # ウォレット
    └── Lesson3.java      # トランザクション
```
