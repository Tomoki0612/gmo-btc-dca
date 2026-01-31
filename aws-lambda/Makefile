.PHONY: build deploy deploy-guided invoke logs clean validate

# SAMビルド
build:
	sam build

# 初回デプロイ（対話形式でパラメータを設定）
deploy-guided: build
	sam deploy --guided

# 通常デプロイ（samconfig.tomlの設定を使用）
deploy: build
	sam deploy

# パラメータを指定してデプロイ
# 使用例: make deploy-with-params API_KEY=xxx API_SECRET=xxx EMAIL=your@email.com AMOUNT=5000
deploy-with-params: build
	sam deploy \
		--parameter-overrides \
		"GmoApiKey=$(API_KEY)" \
		"GmoApiSecret=$(API_SECRET)" \
		"InvestmentAmount=$(AMOUNT)" \
		"NotificationEmail=$(EMAIL)"

# ローカルでLambda関数を実行（env.jsonが必要）
invoke:
	sam local invoke BtcAutoPurchaseFunction --env-vars env.json

# CloudWatch Logsをリアルタイム表示
logs:
	sam logs -n BtcAutoPurchaseFunction --stack-name btc-auto-purchase --tail

# テンプレートの検証
validate:
	sam validate

# ビルド成果物を削除
clean:
	rm -rf .aws-sam

# スタックを削除（注意：すべてのリソースが削除されます）
delete:
	sam delete --stack-name btc-auto-purchase

# ヘルプ
help:
	@echo "使用可能なコマンド:"
	@echo "  make build          - SAMビルド"
	@echo "  make deploy-guided  - 初回デプロイ（対話形式）"
	@echo "  make deploy         - 通常デプロイ"
	@echo "  make deploy-with-params API_KEY=xxx API_SECRET=xxx EMAIL=xxx AMOUNT=xxx"
	@echo "                      - パラメータ指定デプロイ"
	@echo "  make invoke         - ローカル実行"
	@echo "  make logs           - ログ表示"
	@echo "  make validate       - テンプレート検証"
	@echo "  make clean          - ビルド成果物削除"
	@echo "  make delete         - スタック削除"
