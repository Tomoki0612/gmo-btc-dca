package com.example.bitcoinj;

import org.bitcoinj.core.*;
import org.bitcoinj.params.TestNet3Params;
import org.bitcoinj.script.Script;
import org.bitcoinj.script.ScriptBuilder;
import org.bitcoinj.wallet.Wallet;

/**
 * レッスン3: トランザクションの仕組み
 *
 * 学べること:
 * - トランザクション（取引）の構造
 * - Input（入力）と Output（出力）の概念
 * - トランザクションの作成と署名
 * - 手数料の計算
 * - トランザクションIDとハッシュ
 */
public class Lesson3 {

    public static void main(String[] args) throws Exception {
        System.out.println("=== レッスン3: トランザクションの仕組み ===\n");

        NetworkParameters params = TestNet3Params.get();

        // --- 1. トランザクションの基本概念 ---
        System.out.println("【トランザクションとは？】");
        System.out.println("Bitcoinの送金 = トランザクション");
        System.out.println("構造:");
        System.out.println("  Input (入力)  : どこからBTCを使うか（前のトランザクションの出力を参照）");
        System.out.println("  Output (出力) : どこにBTCを送るか（アドレスと金額）");
        System.out.println("  手数料        : Input合計 - Output合計 = マイナーへの手数料");
        System.out.println();

        // --- 2. 空のトランザクションを作成してみる ---
        Transaction tx = new Transaction(params);

        System.out.println("【空のトランザクション】");
        System.out.println("バージョン: " + tx.getVersion());
        System.out.println("入力数: " + tx.getInputs().size());
        System.out.println("出力数: " + tx.getOutputs().size());
        System.out.println("サイズ: " + tx.getMessageSize() + " bytes");
        System.out.println();

        // --- 3. 出力（Output）を追加する ---
        // 送金先アドレスと金額を指定
        ECKey recipientKey = new ECKey();
        Address recipientAddress = LegacyAddress.fromKey(params, recipientKey);
        Coin sendAmount = Coin.parseCoin("0.01"); // 0.01 BTC

        tx.addOutput(sendAmount, recipientAddress);

        System.out.println("【出力を追加】");
        System.out.println("送金先: " + recipientAddress);
        System.out.println("送金額: " + sendAmount.toFriendlyString());
        System.out.println("出力数: " + tx.getOutputs().size());
        System.out.println();

        // --- 4. トランザクションの詳細を確認 ---
        TransactionOutput output = tx.getOutput(0);

        System.out.println("【出力の詳細】");
        System.out.println("金額 (satoshi): " + output.getValue().value);
        System.out.println("金額 (BTC): " + output.getValue().toFriendlyString());
        System.out.println("スクリプト: " + output.getScriptPubKey());
        System.out.println("スクリプトタイプ: " + output.getScriptPubKey().getScriptType());
        System.out.println();

        // --- 5. Scriptの仕組み ---
        System.out.println("【Scriptとは？】");
        System.out.println("Bitcoinではスマートコントラクトの原型として「Script」が使われます。");
        System.out.println("P2PKH Script = 「この公開鍵のハッシュの持ち主だけが使える」");
        System.out.println();

        // P2PKHスクリプトの作成例
        ECKey myKey = new ECKey();
        Script p2pkhScript = ScriptBuilder.createOutputScript(
            LegacyAddress.fromKey(params, myKey)
        );
        System.out.println("P2PKH Script例: " + p2pkhScript);
        System.out.println();

        // --- 6. 手数料について ---
        System.out.println("【手数料の仕組み】");
        System.out.println("手数料 = 入力の合計 - 出力の合計");
        System.out.println("手数料が高い → マイナーに優先的に処理される");
        System.out.println("手数料が低すぎる → 処理されない可能性がある");
        System.out.println();

        // 推奨手数料の例
        Coin minFee = Transaction.REFERENCE_DEFAULT_MIN_TX_FEE;
        System.out.println("最小推奨手数料: " + minFee.toFriendlyString());
        System.out.println("最小推奨手数料 (satoshi): " + minFee.value);
        System.out.println();

        // --- 7. シミュレーション: 完全なトランザクション ---
        System.out.println("【完全なトランザクションのシミュレーション】");
        System.out.println("実際のトランザクション作成には以下が必要:");
        System.out.println("  1. 未使用のトランザクション出力 (UTXO) をInputとして追加");
        System.out.println("  2. 送金先アドレスと金額をOutputとして追加");
        System.out.println("  3. おつりアドレスをOutputとして追加");
        System.out.println("  4. 秘密鍵で署名");
        System.out.println("  5. ネットワークにブロードキャスト");
        System.out.println();

        // ウォレットを使った送金シミュレーション
        Wallet senderWallet = Wallet.createDeterministic(params, Script.ScriptType.P2PKH);
        Address senderAddress = senderWallet.currentReceiveAddress();

        System.out.println("送金元ウォレットアドレス: " + senderAddress);
        System.out.println("送金先アドレス: " + recipientAddress);
        System.out.println("現在の残高: " + senderWallet.getBalance().toFriendlyString());
        System.out.println("※ テストネットで残高がないため、実際の送金はできません");
        System.out.println("※ テストネットのfaucetからBTCを入手すれば送金テスト可能です");

        System.out.println("\n=== レッスン3 完了！ ===");
        System.out.println("おめでとうございます！bitcoinjの基本を学びました。");
        System.out.println();
        System.out.println("【学んだこと まとめ】");
        System.out.println("  Lesson1: 鍵ペア、アドレス、単位（BTC/satoshi）");
        System.out.println("  Lesson2: HDウォレット、ニーモニック、残高確認");
        System.out.println("  Lesson3: トランザクション構造、Input/Output、手数料、Script");
    }
}
