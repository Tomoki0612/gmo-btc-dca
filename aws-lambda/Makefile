.PHONY: build deploy changeset invoke logs-auto logs-settings outputs clean validate help

STACK_NAME := btc-auto-purchase
REGION := ap-northeast-1

build:
	sam build

deploy: build
	sam deploy

changeset: build
	sam deploy --no-execute-changeset --no-confirm-changeset

invoke:
	sam local invoke BtcAutoPurchaseFunction --env-vars auto-purchase/env.json

logs-auto:
	sam logs -n BtcAutoPurchaseFunction --stack-name $(STACK_NAME) --region $(REGION) --tail

logs-settings:
	sam logs -n SettingsApiFunction --stack-name $(STACK_NAME) --region $(REGION) --tail

outputs:
	aws cloudformation describe-stacks \
		--stack-name $(STACK_NAME) \
		--region $(REGION) \
		--query 'Stacks[0].Outputs' \
		--output table

validate:
	sam validate --lint

clean:
	rm -rf .aws-sam

help:
	@echo "使用可能なコマンド:"
	@echo "  make validate       - SAMテンプレートをlint"
	@echo "  make build          - 両LambdaをPython 3.12向けにビルド"
	@echo "  make changeset      - 未実行のCloudFormation変更セットを作成"
	@echo "  make deploy         - プロジェクト全体をSAMでデプロイ"
	@echo "  make invoke         - 自動購入Lambdaをローカル実行"
	@echo "  make logs-auto      - 自動購入Lambdaのログを表示"
	@echo "  make logs-settings  - 設定API Lambdaのログを表示"
	@echo "  make outputs        - スタックOutputsを表示"
	@echo "  make clean          - SAMビルド成果物を削除"
