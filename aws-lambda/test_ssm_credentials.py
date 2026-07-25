import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parent

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-northeast-1")
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parameter_not_found():
    return ClientError(
        {"Error": {"Code": "ParameterNotFound", "Message": "not found"}},
        "GetParameter",
    )


class SettingsApiCredentialsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module(
            "settings_api_lambda",
            ROOT / "settings-api" / "lambda_function.py",
        )

    def setUp(self):
        self.module.table = Mock()
        self.module.history_table = Mock()
        self.module.ssm = Mock()

    def test_get_reports_configuration_without_returning_secrets(self):
        self.module.table.get_item.return_value = {
            "Item": {
                "userId": "user1",
                "amount": 10000,
                "apiKey": "legacy-key",
                "apiSecret": "legacy-secret",
            }
        }
        self.module.ssm.get_parameter.side_effect = parameter_not_found()

        response = self.module.lambda_handler(
            {"httpMethod": "GET", "path": "/settings"},
            None,
        )
        body = json.loads(response["body"])

        self.assertEqual(response["statusCode"], 200)
        self.assertTrue(body["apiConfigured"])
        self.assertNotIn("apiKey", body)
        self.assertNotIn("apiSecret", body)

    def test_post_migrates_legacy_credentials_and_removes_dynamodb_fields(self):
        self.module.table.get_item.return_value = {
            "Item": {
                "userId": "user1",
                "amount": 10000,
                "apiKey": "legacy-key",
                "apiSecret": "legacy-secret",
            }
        }
        self.module.ssm.get_parameter.side_effect = parameter_not_found()

        response = self.module.lambda_handler(
            {
                "httpMethod": "POST",
                "path": "/settings",
                "body": json.dumps({"amount": 20000}),
            },
            None,
        )

        self.assertEqual(response["statusCode"], 200)
        put_parameter = self.module.ssm.put_parameter.call_args.kwargs
        self.assertEqual(put_parameter["Type"], "SecureString")
        self.assertEqual(put_parameter["Tier"], "Standard")
        self.assertEqual(
            json.loads(put_parameter["Value"]),
            {"apiKey": "legacy-key", "apiSecret": "legacy-secret"},
        )
        saved_item = self.module.table.put_item.call_args.kwargs["Item"]
        self.assertEqual(saved_item["amount"], 20000)
        self.assertNotIn("apiKey", saved_item)
        self.assertNotIn("apiSecret", saved_item)


class AutoPurchaseCredentialsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module(
            "auto_purchase_lambda",
            ROOT / "auto-purchase" / "btc_auto_purchase.py",
        )

    def setUp(self):
        self.module.ssm = Mock()
        self.module.sns = Mock()
        self.module.table = Mock()
        self.module.SNS_TOPIC_ARN = "arn:aws:sns:ap-northeast-1:123456789012:test"

    def test_ssm_credentials_take_precedence_over_legacy_values(self):
        self.module.ssm.get_parameter.return_value = {
            "Parameter": {
                "Value": json.dumps(
                    {"apiKey": "ssm-key", "apiSecret": "ssm-secret"}
                )
            }
        }

        credentials = self.module._get_api_credentials(
            {"apiKey": "legacy-key", "apiSecret": "legacy-secret"}
        )

        self.assertEqual(credentials, ("ssm-key", "ssm-secret"))

    def test_notification_prefers_discord_without_sending_email(self):
        self.module.ssm.get_parameter.return_value = {
            "Parameter": {
                "Value": "https://discord.com/api/webhooks/123/token"
            }
        }
        discord_response = Mock()

        with patch.object(
            self.module.requests,
            "post",
            return_value=discord_response,
        ) as post:
            self.module.send_notification("BTC積立成功", "購入しました")

        post.assert_called_once_with(
            "https://discord.com/api/webhooks/123/token",
            json={
                "content": "**BTC積立成功**\n\n購入しました",
                "allowed_mentions": {"parse": []},
            },
            timeout=10,
        )
        discord_response.raise_for_status.assert_called_once_with()
        self.module.sns.publish.assert_not_called()

    def test_notification_falls_back_to_email_when_discord_is_missing(self):
        self.module.ssm.get_parameter.side_effect = parameter_not_found()
        self.module.sns.publish.return_value = {"MessageId": "message-1"}

        with patch.object(self.module.requests, "post") as post:
            self.module.send_notification("BTC積立エラー", "失敗しました")

        post.assert_not_called()
        self.module.sns.publish.assert_called_once_with(
            TopicArn=self.module.SNS_TOPIC_ARN,
            Subject="BTC積立エラー",
            Message="失敗しました",
        )

    def test_notification_can_be_tested_without_running_a_purchase(self):
        with patch.object(self.module, "send_notification") as notify:
            response = self.module.lambda_handler(
                {"action": "test-notification"},
                None,
            )

        self.assertEqual(response["statusCode"], 200)
        notify.assert_called_once_with(
            subject="BTC積立 通知テスト",
            message="Discord通知の設定が完了しました。",
        )
        self.module.table.get_item.assert_not_called()


if __name__ == "__main__":
    unittest.main()
