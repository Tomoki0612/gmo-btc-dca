import io
import re
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

import requests

import btc_purchase


class PurchaseTests(unittest.TestCase):
    def test_monthly_runs_share_an_id_across_manual_and_scheduled_runs(self):
        manual_at = datetime(2026, 11, 10, tzinfo=timezone.utc)
        scheduled_at = datetime(2026, 11, 28, tzinfo=timezone.utc)
        now = datetime(2026, 11, 29, tzinfo=timezone.utc)
        manual_order = btc_purchase.client_order_id("123", manual_at, "monthly", now)
        scheduled_order = btc_purchase.client_order_id("123", scheduled_at, "monthly", now)
        self.assertEqual(manual_order, scheduled_order)
        self.assertTrue(re.fullmatch(r"[A-Za-z0-9]{1,36}", manual_order))

    def test_run_from_a_previous_month_cannot_create_an_order(self):
        with self.assertRaises(ValueError):
            btc_purchase.client_order_id(
                "123",
                datetime(2026, 11, 28, tzinfo=timezone.utc),
                "monthly",
                datetime(2026, 12, 1, tzinfo=timezone.utc),
            )

    @patch("btc_purchase.get_btc_price", return_value=Decimal("8000000"))
    @patch("btc_purchase.private_json")
    def test_success_logs_no_order_identifier(self, api, price):
        api.return_value = {"status": 0, "data": "exchange-order-123"}
        log = io.StringIO()
        with redirect_stdout(log):
            self.assertEqual(btc_purchase.place_order(2000, "myOrderId", "key", "secret"), 0)
        self.assertEqual(api.call_args.kwargs["body"]["clientOrderId"], "myOrderId")
        self.assertNotIn("exchange-order-123", log.getvalue())
        self.assertNotIn("myOrderId", log.getvalue())

    @patch("btc_purchase.get_btc_price", return_value=Decimal("8000000"))
    @patch("btc_purchase.private_json")
    def test_uncertain_or_duplicate_order_is_only_looked_up(self, api, price):
        for reply in (requests.Timeout("private text"), {"status": 1, "messages": [
            {"message_code": "ERR-915", "message_string": "private text"},
        ]}):
            with self.subTest(reply_type=type(reply).__name__):
                api.reset_mock()
                api.side_effect = [
                    reply,
                    {"status": 0, "data": {"list": [{"clientOrderId": "myOrderId"}]}},
                ]
                log = io.StringIO()
                with redirect_stdout(log):
                    self.assertEqual(btc_purchase.place_order(2000, "myOrderId", "key", "secret"), 0)
                self.assertEqual([call.args[0] for call in api.call_args_list], ["POST", "GET"])
                self.assertEqual(api.call_args.kwargs, {"params": {"clientOrderId": "myOrderId"}})
                self.assertNotIn("private text", log.getvalue())

    @patch("btc_purchase.get_btc_price", return_value=Decimal("8000000"))
    @patch("btc_purchase.private_json")
    def test_unconfirmed_order_fails_without_a_second_post(self, api, price):
        api.side_effect = [requests.Timeout(), {"status": 0, "data": {"list": []}}]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(btc_purchase.place_order(2000, "myOrderId", "key", "secret"), 1)
        self.assertEqual([call.args[0] for call in api.call_args_list], ["POST", "GET"])


if __name__ == "__main__":
    unittest.main()
