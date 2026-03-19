package com.example.bitcoinj;

import org.bitcoinj.core.*;
import org.bitcoinj.params.TestNet3Params;
import org.bitcoinj.script.Script;
import org.bitcoinj.wallet.Wallet;
import org.bitcoinj.wallet.DeterministicSeed;

import java.security.SecureRandom;
import java.util.List;

/**
 * レッスン2: ウォレットの作成と管理
 *
 * 学べること:
 * - HDウォレット（階層的決定性ウォレット）の概念
 * - ニーモニック（復元フレーズ）の生成
 * - ウォレットからのアドレス生成
 * - ウォレットの情報表示
 */
public class Lesson2 {

    public static void main(String[] args) {
        System.out.println("=== レッスン2: ウォレットの作成と管理 ===\n");

        NetworkParameters params = TestNet3Params.get();

        // --- 1. 新しいウォレットの作成 ---
        // Wallet.createDeterministic() でHDウォレットを作成
        // P2PKH = Pay-to-Public-Key-Hash（従来のアドレス形式）
        Wallet wallet = Wallet.createDeterministic(params, Script.ScriptType.P2PKH);

        System.out.println("【ウォレット作成】");
        System.out.println("ウォレットが作成されました！");
        System.out.println();

        // --- 2. ニーモニック（復元フレーズ） ---
        // 12個の英単語で秘密鍵を復元できる仕組み（BIP39）
        // これがあれば、ウォレットを完全に復元可能
        DeterministicSeed seed = wallet.getKeyChainSeed();
        List<String> mnemonicWords = seed.getMnemonicCode();

        System.out.println("【ニーモニック（復元フレーズ）】");
        System.out.println("⚠️ 実際のウォレットではこれを安全に保管してください！");
        System.out.println("単語数: " + (mnemonicWords != null ? mnemonicWords.size() : 0));
        if (mnemonicWords != null) {
            for (int i = 0; i < mnemonicWords.size(); i++) {
                System.out.printf("  %2d. %s%n", i + 1, mnemonicWords.get(i));
            }
        }
        System.out.println("作成日時: " + seed.getCreationTimeSeconds() + " (unix timestamp)");
        System.out.println();

        // --- 3. ウォレットのアドレス ---
        // HDウォレットは1つのシードから複数のアドレスを生成できる
        Address currentAddress = wallet.currentReceiveAddress();
        Address freshAddress = wallet.freshReceiveAddress();

        System.out.println("【ウォレットのアドレス】");
        System.out.println("現在の受取アドレス: " + currentAddress);
        System.out.println("新しい受取アドレス: " + freshAddress);
        System.out.println();

        // --- 4. ウォレットの残高 ---
        // 新しいウォレットなので残高は0
        Coin balance = wallet.getBalance();
        Coin estimatedBalance = wallet.getBalance(Wallet.BalanceType.ESTIMATED);

        System.out.println("【残高】");
        System.out.println("確定残高: " + balance.toFriendlyString());
        System.out.println("推定残高: " + estimatedBalance.toFriendlyString());
        System.out.println();

        // --- 5. ウォレットの鍵情報 ---
        System.out.println("【鍵の管理】");
        System.out.println("管理している鍵の数: " + wallet.getImportedKeys().size() + " (インポート済み)");
        System.out.println("最古の鍵の作成時刻: " + wallet.getEarliestKeyCreationTime());
        System.out.println();

        // --- 6. ウォレットの説明（toString） ---
        System.out.println("【ウォレット概要】");
        String walletInfo = wallet.toString(
            false,  // includePrivateKeys
            false,  // includeTransactions
            false,  // includeExtensions
            null    // chain
        );
        // 先頭の数行だけ表示
        String[] lines = walletInfo.split("\n");
        for (int i = 0; i < Math.min(lines.length, 10); i++) {
            System.out.println("  " + lines[i]);
        }

        System.out.println("\n=== レッスン2 完了！ ===");
        System.out.println("次は Lesson3 でトランザクションの仕組みを学びましょう。");
        System.out.println("実行: ./gradlew runLesson3");
    }
}
