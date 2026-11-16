import importlib.util
import json
import os
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

from botocore.exceptions import ClientError


ROOT = Path(__file__).resolve().parent
AUTHORIZED_SUB = "00000000-0000-4000-8000-000000000001"

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


def authorized_event(**fields):
    return {
        "requestContext": {"authorizer": {"claims": {"sub": AUTHORIZED_SUB}}},
        **fields,
    }


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
        self.module.AUTHORIZED_USER_SUB = AUTHORIZED_SUB

    def test_get_reports_configuration_without_returning_secrets(self):
        self.module.table.get_item.return_value = {
            "Item": {
                "userId": "user1",
                "amount": 10000,
                "frequency": "monthly",
                "scheduleDay": 1,
                "scheduleTime": 9,
                "apiKey": "legacy-key",
                "apiSecret": "legacy-secret",
            }
        }
        self.module.ssm.get_parameter.side_effect = parameter_not_found()

        response = self.module.lambda_handler(
            authorized_event(httpMethod="GET", path="/settings"),
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
                "frequency": "monthly",
                "scheduleDay": 1,
                "scheduleTime": 9,
                "apiKey": "legacy-key",
                "apiSecret": "legacy-secret",
            }
        }
        self.module.ssm.get_parameter.side_effect = parameter_not_found()

        with patch.object(self.module, "_fetch_assets", return_value=[]):
            response = self.module.lambda_handler(
                authorized_event(httpMethod="POST", path="/settings", body=json.dumps({"amount": 20000})),
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

    def test_rejects_invalid_schedule_before_saving(self):
        self.module.table.get_item.return_value = {
            "Item": {
                "userId": "user1",
                "amount": 10000,
                "frequency": "monthly",
                "scheduleDay": 1,
                "scheduleTime": 9,
            }
        }

        response = self.module.lambda_handler(
            authorized_event(httpMethod="POST", path="/settings", body=json.dumps({"scheduleTime": 24})),
            None,
        )

        self.assertEqual(response["statusCode"], 400)
        self.module.table.put_item.assert_not_called()

    def test_history_excludes_legacy_dry_runs_from_purchase_totals(self):
        self.module.history_table.query.return_value = {"Items": [
            {"sk": "test", "type": "purchase", "status": "ok", "orderId": "DRY_RUN", "amount": 10000},
            {"sk": "real", "type": "purchase", "status": "ok", "orderId": "123", "amount": 10005},
            {"sk": "change", "type": "change", "field": "amount"},
        ]}
        response = self.module.lambda_handler(authorized_event(httpMethod="GET", path="/history"), None)
        items = json.loads(response["body"])["items"]
        self.assertEqual([row["id"] for row in items], ["real", "change"])

    def test_rejects_another_cognito_user(self):
        self.module.AUTHORIZED_USER_SUB = "allowed-sub"

        response = self.module.lambda_handler(
            {
                "httpMethod": "GET",
                "path": "/settings",
                "requestContext": {
                    "authorizer": {"claims": {"sub": "different-sub"}}
                },
            },
            None,
        )

        self.assertEqual(response["statusCode"], 403)
        self.module.table.get_item.assert_not_called()

    def test_rejects_missing_allowlist_or_invalid_claims_before_any_data_access(self):
        contexts = [
            {},
            {"requestContext": None},
            {"requestContext": {"authorizer": None}},
            {"requestContext": {"authorizer": {"claims": None}}},
            {"requestContext": {"authorizer": {"claims": "invalid"}}},
            {"requestContext": {"authorizer": {"claims": {}}}},
            {"requestContext": {"authorizer": {"claims": {"sub": "different-sub"}}}},
        ]
        cases = [(AUTHORIZED_SUB, context) for context in contexts]
        cases.append(("", authorized_event()))
        for allowed_sub, context in cases:
            self.module.AUTHORIZED_USER_SUB = allowed_sub
            for method, path in (("GET", "/settings"), ("POST", "/settings"),
                                 ("GET", "/balance"), ("GET", "/history")):
                with self.subTest(allowed_sub=allowed_sub, context=context, method=method, path=path):
                    response = self.module.lambda_handler(
                        {**context, "httpMethod": method, "path": path, "body": "{}"}, None,
                    )
                    self.assertEqual(response["statusCode"], 403)
                    for client in (self.module.table, self.module.history_table, self.module.ssm):
                        self.assertEqual(client.mock_calls, [])

    def test_cors_preflight_remains_available_without_authentication(self):
        self.module.AUTHORIZED_USER_SUB = ""
        response = self.module.lambda_handler({"httpMethod": "OPTIONS", "path": "/settings"}, None)
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(self.module.table.mock_calls, [])
        self.assertEqual(self.module.ssm.mock_calls, [])

    def test_rejects_credentials_that_gmo_does_not_accept(self):
        self.module.table.get_item.return_value = {"Item": {"userId": "user1"}}
        self.module.ssm.get_parameter.side_effect = parameter_not_found()

        with patch.object(self.module, "_fetch_assets", side_effect=RuntimeError("invalid key")):
            response = self.module.lambda_handler(
                authorized_event(httpMethod="POST", path="/settings", body=json.dumps({"apiKey": "bad", "apiSecret": "bad"})),
                None,
            )

        self.assertEqual(response["statusCode"], 400)
        self.module.ssm.put_parameter.assert_not_called()


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
        self.module.execution_table = Mock()
        self.module.history_table = Mock()
        self.module.SNS_TOPIC_ARN = "arn:aws:sns:ap-northeast-1:123456789012:test"
        self.module.DRY_RUN = "true"
        self.module._context = None

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
            timeout=(2, 6),
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

    def test_http_notification_errors_do_not_log_webhook_secrets(self):
        webhook_url = "https://discord.com/api/webhooks/123/private-webhook-token"
        self.module.ssm.get_parameter.return_value = {"Parameter": {"Value": webhook_url}}
        self.module.sns.publish.return_value = {"MessageId": "fallback-message"}
        for status in (401, 404, 429, 500):
            with self.subTest(status=status):
                response = self.module.requests.Response()
                response.status_code = status
                response.url = webhook_url
                response.reason = "DO_NOT_LOG"
                with patch.object(self.module.requests, "post", return_value=response), patch("builtins.print") as log:
                    self.assertTrue(self.module.send_notification("BTC積立エラー", "失敗しました"))
                logged = "\n".join(str(call) for call in log.call_args_list)
                self.assertIn(f"HTTP {status}", logged)
                self.assertIn("HTTPError", logged)
                self.assertNotIn(webhook_url, logged)
                self.assertNotIn("private-webhook-token", logged)
                self.assertNotIn("DO_NOT_LOG", logged)
        self.assertEqual(self.module.sns.publish.call_count, 4)

    def test_network_notification_errors_do_not_log_webhook_secrets(self):
        webhook_url = "https://discord.com/api/webhooks/123/private-webhook-token"
        self.module.ssm.get_parameter.return_value = {"Parameter": {"Value": webhook_url}}
        self.module.sns.publish.return_value = {"MessageId": "fallback-message"}
        for exception in (self.module.requests.exceptions.Timeout, self.module.requests.exceptions.ConnectionError):
            with self.subTest(exception=exception.__name__):
                with patch.object(self.module.requests, "post", side_effect=exception(webhook_url)), patch("builtins.print") as log:
                    self.assertTrue(self.module.send_notification("BTC積立エラー", "失敗しました"))
                logged = "\n".join(str(call) for call in log.call_args_list)
                self.assertIn(exception.__name__, logged)
                self.assertNotIn(webhook_url, logged)
                self.assertNotIn("private-webhook-token", logged)

    def test_email_notification_error_does_not_log_exception_text(self):
        self.module.ssm.get_parameter.side_effect = parameter_not_found()
        self.module.sns.publish.side_effect = RuntimeError("private-webhook-token")
        with patch("builtins.print") as log:
            self.assertFalse(self.module.send_notification("BTC積立エラー", "失敗しました"))
        logged = "\n".join(str(call) for call in log.call_args_list)
        self.assertIn("RuntimeError", logged)
        self.assertNotIn("private-webhook-token", logged)

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

    def test_order_size_is_floored_to_exchange_step(self):
        self.module.API_KEY = "key"
        self.module.API_SECRET = "secret"
        with patch.object(self.module, "get_btc_price", return_value=Decimal("12345678")):
            order_id, _, size = self.module.place_order(10000)

        self.assertEqual(order_id, "DRY_RUN")
        self.assertEqual(size, Decimal("0.00081"))
        self.assertLessEqual(size * Decimal("12345678"), Decimal("10000"))

    def test_unparseable_order_response_is_uncertain(self):
        self.module.API_KEY = "key"
        self.module.API_SECRET = "secret"
        self.module.DRY_RUN = "false"
        response = Mock()
        response.json.side_effect = json.JSONDecodeError("invalid", "", 0)

        with patch.object(
            self.module, "get_btc_price", return_value=Decimal("10000000")
        ), patch.object(self.module.requests, "post", return_value=response):
            with self.assertRaises(self.module.OrderSubmissionUncertain):
                self.module.place_order(10000)

    def test_success_response_without_order_id_is_uncertain(self):
        self.module.API_KEY = "key"
        self.module.API_SECRET = "secret"
        self.module.DRY_RUN = "false"
        response = Mock()
        response.json.return_value = {"status": 0}

        with patch.object(
            self.module, "get_btc_price", return_value=Decimal("10000000")
        ), patch.object(self.module.requests, "post", return_value=response):
            with self.assertRaises(self.module.OrderSubmissionUncertain):
                self.module.place_order(10000)

    def test_reconciliation_uses_actual_executions(self):
        responses = [
            {"list": [{"status": "EXECUTED"}]},
            {
                "list": [
                    {"size": "0.0004", "price": "10000000", "fee": "2"},
                    {"size": "0.0006", "price": "11000000", "fee": "3"},
                ]
            },
        ]
        with patch.object(self.module, "_private_get", side_effect=responses):
            result = self.module._wait_for_execution("123", attempts=1, delay=0)

        self.assertEqual(result["btc"], Decimal("0.0010"))
        self.assertEqual(result["gross"], Decimal("10600.0000"))
        self.assertEqual(result["rate"], Decimal("10600000"))
        self.assertEqual(result["fee"], Decimal("5"))

    def test_duplicate_schedule_slot_is_rejected(self):
        self.module.execution_table.put_item.side_effect = ClientError(
            {"Error": {"Code": "ConditionalCheckFailedException", "Message": "duplicate"}},
            "PutItem",
        )

        with self.assertRaises(self.module.DuplicateExecution):
            self.module._acquire_execution(self.module.datetime.now(self.module.JST))

    def test_invalid_frequency_never_claims_or_places_order(self):
        self.module.table.get_item.return_value = {
            "Item": {
                "userId": "user1",
                "amount": 10000,
                "frequency": "hourly",
                "scheduleDay": 1,
                "scheduleTime": 9,
            }
        }
        self.module.ssm.get_parameter.return_value = {
            "Parameter": {"Value": json.dumps({"apiKey": "key", "apiSecret": "secret"})}
        }

        with patch.object(self.module, "send_notification"), patch.object(
            self.module, "_put_purchase_history"
        ):
            response = self.module.lambda_handler({}, None)

        self.assertEqual(response["statusCode"], 500)
        self.module.execution_table.put_item.assert_not_called()

    def test_success_history_uses_actual_execution_values(self):
        now = self.module.datetime.now(self.module.JST)
        self.module.table.get_item.return_value = {
            "Item": {
                "userId": "user1",
                "amount": 10000,
                "frequency": "daily",
                "scheduleTime": now.hour,
            }
        }
        self.module.ssm.get_parameter.return_value = {
            "Parameter": {"Value": json.dumps({"apiKey": "key", "apiSecret": "secret"})}
        }
        self.module.DRY_RUN = "false"
        execution = {
            "btc": Decimal("0.001"),
            "rate": Decimal("10000000"),
            "gross": Decimal("10000"),
            "fee": Decimal("5"),
            "orderStatus": "EXECUTED",
        }

        with patch.object(
            self.module,
            "place_order",
            return_value=("123", Decimal("9990000"), Decimal("0.001")),
        ), patch.object(
            self.module, "_wait_for_execution", return_value=execution
        ), patch.object(
            self.module, "get_account_balance", return_value=50000
        ), patch.object(
            self.module, "send_notification"
        ), patch.object(
            self.module, "_put_purchase_history"
        ) as history, patch.object(self.module.time, "sleep"):
            response = self.module.lambda_handler({}, None)

        self.assertEqual(response["statusCode"], 200)
        self.assertEqual([call.kwargs["status"] for call in history.call_args_list], ["pending", "pending", "ok"])
        final = history.call_args.kwargs
        self.assertEqual(final["amount_jpy"], 10005)
        self.assertEqual(final["btc"], Decimal("0.001"))
        self.assertEqual(final["rate"], Decimal("10000000"))
        self.assertEqual(final["order_id"], "123")
        self.assertEqual(final["fee"], Decimal("5"))
        self.assertEqual(final["requested_amount"], 10000)
        self.assertEqual(len({call.kwargs["history_key"] for call in history.call_args_list}), 1)

    def test_order_timeout_is_marked_for_manual_confirmation(self):
        now = self.module.datetime.now(self.module.JST)
        self.module.table.get_item.return_value = {
            "Item": {
                "userId": "user1",
                "amount": 10000,
                "frequency": "daily",
                "scheduleTime": now.hour,
            }
        }
        self.module.ssm.get_parameter.return_value = {
            "Parameter": {"Value": json.dumps({"apiKey": "key", "apiSecret": "secret"})}
        }
        self.module.DRY_RUN = "false"

        with patch.object(
            self.module,
            "place_order",
            side_effect=self.module.OrderSubmissionUncertain("timeout"),
        ), patch.object(self.module, "send_notification") as notify, patch.object(
            self.module, "_put_purchase_history"
        ) as history:
            response = self.module.lambda_handler({}, None)

        self.assertEqual(response["statusCode"], 500)
        self.assertEqual(history.call_args.kwargs["status"], "pending")
        self.assertEqual(notify.call_args.kwargs["subject"], "BTC積立 要確認")


if __name__ == "__main__":
    unittest.main()
