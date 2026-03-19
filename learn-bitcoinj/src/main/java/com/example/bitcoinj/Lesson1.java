package com.example.bitcoinj;

import org.bitcoinj.core.*;
import org.bitcoinj.params.MainNetParams;
import org.bitcoinj.params.TestNet3Params;

/**
 * レッスン1: Bitcoinの基本概念
 *
 * 学べること:
 * - ネットワークパラメータ（メインネット / テストネット）
 * - 秘密鍵と公開鍵の生成
 * - Bitcoinアドレスの仕組み
 * - Satoshi と BTC の単位変換
 */
public class Lesson1 {

    public static void main(String[] args) {
        System.out.println("=== レッスン1: Bitcoinの基本 ===\n");

        // --- 1. ネットワークの選択 ---
        // メインネット: 本番（実際のBTC）
        // テストネット: テスト用（無料で入手可能）
        NetworkParameters mainnet = MainNetParams.get();
        NetworkParameters testnet = TestNet3Params.get();

        System.out.println("【ネットワーク】");
        System.out.println("メインネットID: " + mainnet.getId());
        System.out.println("テストネットID: " + testnet.getId());
        System.out.println();

        // --- 2. 鍵ペアの生成 ---
        // ECKey = 楕円曲線暗号の鍵ペア（秘密鍵 + 公開鍵）
        ECKey key = new ECKey();

        System.out.println("【鍵ペア】");
        System.out.println("秘密鍵 (hex): " + key.getPrivateKeyAsHex());
        System.out.println("公開鍵 (hex): " + key.getPublicKeyAsHex());
        System.out.println("秘密鍵 (WIF, メインネット): " + key.getPrivateKeyEncoded(mainnet));
        System.out.println("秘密鍵 (WIF, テストネット): " + key.getPrivateKeyEncoded(testnet));
        System.out.println();

        // --- 3. アドレスの生成 ---
        // 同じ鍵ペアでも、ネットワークによってアドレスが変わる
        // メインネットアドレスは "1" または "3" で始まる
        // テストネットアドレスは "m" または "n" で始まる
        LegacyAddress mainnetAddress = LegacyAddress.fromKey(mainnet, key);
        LegacyAddress testnetAddress = LegacyAddress.fromKey(testnet, key);

        System.out.println("【アドレス】");
        System.out.println("メインネットアドレス: " + mainnetAddress);
        System.out.println("テストネットアドレス: " + testnetAddress);
        System.out.println();

        // --- 4. 単位変換 ---
        // 1 BTC = 100,000,000 Satoshi (= 10^8 Satoshi)
        // bitcoinj内部ではSatoshi単位で計算する
        Coin oneBtc = Coin.COIN;                        // 1 BTC
        Coin halfBtc = Coin.COIN.divide(2);              // 0.5 BTC
        Coin tenThousandSat = Coin.valueOf(10_000);      // 10,000 satoshi
        Coin fromBtcString = Coin.parseCoin("0.005");    // 文字列からパース

        System.out.println("【単位変換】");
        System.out.println("1 BTC = " + oneBtc.toFriendlyString());
        System.out.println("1 BTC = " + oneBtc.value + " satoshi");
        System.out.println("0.5 BTC = " + halfBtc.toFriendlyString());
        System.out.println("10,000 satoshi = " + tenThousandSat.toFriendlyString());
        System.out.println("0.005 BTC = " + fromBtcString.value + " satoshi");
        System.out.println();

        // --- 5. 複数のアドレスを生成してみる ---
        System.out.println("【複数アドレスの生成】");
        for (int i = 1; i <= 3; i++) {
            ECKey newKey = new ECKey();
            LegacyAddress addr = LegacyAddress.fromKey(testnet, newKey);
            System.out.println("アドレス" + i + ": " + addr);
        }

        System.out.println("\n=== レッスン1 完了！ ===");
        System.out.println("次は Lesson2 でウォレットの作成を学びましょう。");
        System.out.println("実行: ./gradlew runLesson2");
    }
}
