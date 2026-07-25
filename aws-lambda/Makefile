.PHONY: build deploy changeset configure-discord test-discord invoke logs-auto logs-settings outputs clean validate help

STACK_NAME := btc-auto-purchase
REGION := ap-northeast-1

build:
	sam build

deploy: build
	sam deploy

changeset: build
	sam deploy --no-execute-changeset --no-confirm-changeset

configure-discord:
	@read -r -s -p "Discord Webhook URL: " discord_webhook_url; \
	echo; \
	case "$$discord_webhook_url" in \
		https://discord.com/api/webhooks/*|https://discordapp.com/api/webhooks/*) ;; \
		*) echo "Discord Webhook URLの形式が正しくありません" >&2; exit 1 ;; \
	esac; \
	aws ssm put-parameter \
		--name /gmo-btc-dca/prod/discord-webhook-url \
		--value "$$discord_webhook_url" \
		--type SecureString \
		--tier Standard \
		--overwrite \
		--region $(REGION) >/dev/null; \
	unset discord_webhook_url; \
	echo "Discord Webhook URLをSSMへ保存しました"

test-discord:
	aws lambda invoke \
		--function-name btc-auto-purchase \
		--cli-binary-format raw-in-base64-out \
		--payload '{"action":"test-notification"}' \
		--region $(REGION) \
		/tmp/btc-dca-discord-test.json >/dev/null
	@cat /tmp/btc-dca-discord-test.json

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
	@echo "  make configure-discord - Webhook URLをSSM SecureStringへ保存"
	@echo "  make test-discord   - 購入せずDiscord通知だけをテスト"
	@echo "  make invoke         - 自動購入Lambdaをローカル実行"
	@echo "  make logs-auto      - 自動購入Lambdaのログを表示"
	@echo "  make logs-settings  - 設定API Lambdaのログを表示"
	@echo "  make outputs        - スタックOutputsを表示"
	@echo "  make clean          - SAMビルド成果物を削除"
