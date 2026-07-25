import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import Mock

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

    def test_ssm_credentials_take_precedence_over_legacy_values(self):
        self.module.ssm = Mock()
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


if __name__ == "__main__":
    unittest.main()
