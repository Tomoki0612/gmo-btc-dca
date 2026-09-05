"""Regression tests: all AWS/exchange/notification I/O is replaced in memory."""
import copy
import json
import unittest
from contextlib import ExitStack
from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock, patch

import test_ssm_credentials as fixtures


class SimulatedLambdaTermination(BaseException):
    """A hard deadline does not run the handler's except Exception block."""


class PurchaseRecoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = fixtures.load_module(
            "purchase_recovery", fixtures.ROOT / "auto-purchase" / "btc_auto_purchase.py"
        )

    def setUp(self):
        self.m = self.module
        self.m._context = None
        self.m.DRY_RUN = "false"
        self.m.API_KEY, self.m.API_SECRET = "key", "secret"
        self.now = self.m.datetime.now(self.m.JST)
        self.records = {}
        self.history = {}
        self.m.table = Mock()
        self.m.table.get_item.return_value = {"Item": {
            "amount": 10000, "frequency": "daily", "scheduleTime": self.now.hour,
        }}
        self.m.execution_table = Mock()
        self.m.execution_table.put_item.side_effect = self.put_execution
        self.m.execution_table.update_item.side_effect = self.update_execution
        self.m.execution_table.scan.side_effect = self.scan_executions
        self.m.history_table = Mock()
        self.m.history_table.put_item.side_effect = lambda Item: self.history.update({Item["sk"]: copy.deepcopy(Item)})
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(self.m, "_get_api_credentials", return_value=("key", "secret")))
        self.stack.enter_context(patch.object(self.m, "get_btc_price", return_value=Decimal("10000000")))
        self.balance = self.stack.enter_context(patch.object(self.m, "get_account_balance", return_value=50000))
        self.notify = self.stack.enter_context(patch.object(self.m, "send_notification", return_value=True))
        self.post = self.stack.enter_context(patch.object(self.m.requests, "post"))
        self.post.return_value.json.return_value = {"status": 0, "data": "123"}
        self.get = self.stack.enter_context(patch.object(self.m.requests, "get"))
        self.get.side_effect = AssertionError("Unexpected HTTP GET")
        self.fill = {"btc": Decimal("0.001"), "rate": Decimal("10000000"),
                     "gross": Decimal("10000"), "fee": Decimal("5"), "orderStatus": "EXECUTED"}
        self.real_wait = self.m._wait_for_execution
        self.wait = self.stack.enter_context(patch.object(self.m, "_wait_for_execution", return_value=self.fill))

    def put_execution(self, Item, **kwargs):
        if Item["executionKey"] in self.records:
            raise self.conflict()
        self.records[Item["executionKey"]] = copy.deepcopy(Item)

    def update_execution(self, Key, UpdateExpression, ExpressionAttributeValues,
                         ExpressionAttributeNames=None, ConditionExpression=None, **kwargs):
        record = self.records[Key["executionKey"]]
        if ConditionExpression and record.get("reconcileUntil", 0) >= ExpressionAttributeValues[":now"]:
            raise self.conflict()
        names = ExpressionAttributeNames or {}
        for assignment in UpdateExpression.removeprefix("SET ").split(", "):
            name, value = assignment.split(" = ")
            record[names.get(name, name)] = ExpressionAttributeValues[value]
        return {"Attributes": copy.deepcopy(record)}

    def scan_executions(self, **kwargs):
        cutoff = (self.m.datetime.now(self.m.JST) - timedelta(minutes=5)).isoformat(timespec="seconds")
        return {"Items": [copy.deepcopy(r) for r in self.records.values()
                          if r["startedAt"] < cutoff and (r["status"] in {
                              "started", "submitting", "ordered", "reconciliation_pending"
                          } or r.get("notificationPending"))]}

    def conflict(self):
        return fixtures.ClientError({"Error": {"Code": "ConditionalCheckFailedException"}}, "UpdateItem")

    def stale_record(self):
        record = next(iter(self.records.values()))
        record["startedAt"] = (self.now - timedelta(hours=1)).isoformat(timespec="seconds")
        record.pop("reconcileUntil", None)
        return record

    def reconcile(self):
        return self.m.lambda_handler({"action": "reconcile"}, None)

    def test_dry_run_has_no_purchase_records_locks_or_private_requests(self):
        self.m.DRY_RUN = "true"
        response = self.m.lambda_handler({}, None)
        self.assertTrue(json.loads(response["body"])["dry_run"])
        self.assertEqual(self.records, {})
        self.assertEqual(self.history, {})
        self.post.assert_not_called()
        self.wait.assert_not_called()
        self.balance.assert_not_called()
        self.assertIn("DRY_RUN", self.notify.call_args.kwargs["subject"])
        self.assertIn("実注文は行っていません", self.notify.call_args.kwargs["message"])

    def test_dry_run_does_not_block_real_purchase_in_same_hour(self):
        self.m.DRY_RUN = "true"
        self.m.lambda_handler({}, None)
        self.m.DRY_RUN = "false"
        self.assertEqual(self.m.lambda_handler({}, None)["statusCode"], 200)
        self.assertEqual(len(self.records), 1)
        self.assertEqual(len(self.history), 1)
        self.post.assert_called_once()
        self.assertEqual(next(iter(self.history.values()))["status"], "ok")

    def test_failed_dry_run_does_not_create_real_failure_history(self):
        self.m.DRY_RUN = "true"
        with patch.object(self.m, "get_btc_price", side_effect=RuntimeError("price unavailable")):
            self.assertEqual(self.m.lambda_handler({}, None)["statusCode"], 500)
        self.assertEqual(self.history, {})
        self.assertEqual(self.records, {})
        self.assertIn("テストエラー", self.notify.call_args.kwargs["subject"])
        self.post.assert_not_called()

    def test_dry_run_reconciliation_does_not_touch_production_data(self):
        self.m.DRY_RUN = "true"
        self.reconcile()
        self.m.execution_table.scan.assert_not_called()
        self.m.table.get_item.assert_not_called()
        self.assertEqual(self.history, {})

    def test_no_order_is_sent_when_pending_history_cannot_be_saved(self):
        self.m.history_table.put_item.side_effect = RuntimeError("DynamoDB unavailable")
        self.assertEqual(self.m.lambda_handler({}, None)["statusCode"], 500)
        self.post.assert_not_called()

    def test_success_is_durable_before_optional_balance_and_notification(self):
        def check_durable(*args, **kwargs):
            self.assertEqual(next(iter(self.history.values()))["status"], "ok")
            self.assertEqual(next(iter(self.records.values()))["status"], "succeeded")
            return 50000
        self.balance.side_effect = check_durable
        self.notify.side_effect = check_durable
        self.m.lambda_handler({}, None)
        self.assertEqual(len(self.history), 1)
        self.assertEqual(next(iter(self.history.values()))["amount"], 10005)

    def test_balance_failure_cannot_downgrade_success(self):
        self.balance.side_effect = RuntimeError("balance unavailable")
        self.assertEqual(self.m.lambda_handler({}, None)["statusCode"], 200)
        self.assertEqual(next(iter(self.history.values()))["status"], "ok")
        self.assertEqual(next(iter(self.records.values()))["status"], "succeeded")

    def test_hard_timeout_after_order_id_is_reconciled_without_resubmission(self):
        self.wait.side_effect = SimulatedLambdaTermination()
        with self.assertRaises(SimulatedLambdaTermination):
            self.m.lambda_handler({}, None)
        self.assertEqual(next(iter(self.history.values()))["status"], "pending")
        self.assertEqual(next(iter(self.history.values()))["orderId"], "123")
        self.stale_record()
        self.wait.side_effect = None
        self.reconcile()
        self.reconcile()
        self.assertEqual(len(self.history), 1)
        self.assertEqual(next(iter(self.history.values()))["status"], "ok")
        self.post.assert_called_once()

    def test_hard_timeout_during_post_leaves_manual_confirmation_record(self):
        self.post.side_effect = SimulatedLambdaTermination()
        with self.assertRaises(SimulatedLambdaTermination):
            self.m.lambda_handler({}, None)
        self.assertEqual(next(iter(self.history.values()))["status"], "pending")
        self.stale_record()
        self.reconcile()
        self.assertEqual(next(iter(self.records.values()))["status"], "manual_required")
        self.assertEqual(next(iter(self.history.values()))["status"], "pending")
        self.assertIn("要確認", self.notify.call_args.kwargs["subject"])
        self.post.assert_called_once()
        self.wait.assert_not_called()

    def test_termination_between_history_and_state_writes_does_not_double_total(self):
        original = self.update_execution
        def stop_before_success(**kwargs):
            if kwargs["ExpressionAttributeValues"].get(":status") == "succeeded":
                raise SimulatedLambdaTermination()
            return original(**kwargs)
        self.m.execution_table.update_item.side_effect = stop_before_success
        with self.assertRaises(SimulatedLambdaTermination):
            self.m.lambda_handler({}, None)
        self.assertEqual(next(iter(self.history.values()))["status"], "ok")
        self.m.execution_table.update_item.side_effect = original
        self.stale_record()
        self.reconcile()
        self.assertEqual(len(self.history), 1)
        self.assertEqual(next(iter(self.records.values()))["actualAmount"], Decimal("10005"))
        self.post.assert_called_once()

    def test_failed_success_notification_is_retried_without_order_or_history_duplication(self):
        self.notify.return_value = False
        self.m.lambda_handler({}, None)
        record = self.stale_record()
        self.assertTrue(record["notificationPending"])
        self.notify.return_value = True
        self.reconcile()
        self.assertFalse(record["notificationPending"])
        self.assertEqual(self.notify.call_count, 2)
        self.assertEqual(len(self.history), 1)
        self.post.assert_called_once()
        self.wait.assert_called_once()

    def test_reconciliation_lease_skips_another_worker(self):
        self.wait.side_effect = SimulatedLambdaTermination()
        with self.assertRaises(SimulatedLambdaTermination):
            self.m.lambda_handler({}, None)
        record = self.stale_record()
        record["reconcileUntil"] = int(self.m.time.time()) + 180
        self.wait.reset_mock(side_effect=True)
        self.reconcile()
        self.wait.assert_not_called()
        self.assertEqual(record["status"], "ordered")
        self.post.assert_called_once()

    def test_reconciliation_failure_retains_pending_history_and_sends_warning(self):
        self.wait.side_effect = SimulatedLambdaTermination()
        with self.assertRaises(SimulatedLambdaTermination):
            self.m.lambda_handler({}, None)
        record = self.stale_record()
        self.wait.side_effect = RuntimeError("exchange temporarily unavailable")
        self.reconcile()
        self.assertEqual(record["status"], "reconciliation_pending")
        self.assertEqual(next(iter(self.history.values()))["status"], "pending")
        self.assertIn("要確認", self.notify.call_args.kwargs["subject"])
        self.post.assert_called_once()

    def test_no_order_or_lock_when_invocation_has_insufficient_time(self):
        context = Mock()
        context.get_remaining_time_in_millis.return_value = 54000
        self.m.lambda_handler({}, context)
        self.assertEqual(self.records, {})
        self.post.assert_not_called()

    def test_timeouts_shrink_with_remaining_time_and_preserve_recording_budget(self):
        context = Mock()
        self.m._context = context
        context.get_remaining_time_in_millis.return_value = 35000
        self.assertEqual(sum(self.m._http_timeout()), 5)
        context.get_remaining_time_in_millis.return_value = 31000
        with self.assertRaises(self.m.ExecutionBudgetExceeded):
            self.m.place_order(10000)
        self.post.assert_not_called()

    def test_poll_budget_exhaustion_is_pending_and_keeps_order_id(self):
        self.wait.side_effect = self.m.ExecutionBudgetExceeded("low remaining time")
        self.m.lambda_handler({}, None)
        row = next(iter(self.history.values()))
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["orderId"], "123")
        self.assertEqual(next(iter(self.records.values()))["status"], "reconciliation_pending")
        self.post.assert_called_once()

    def test_reconciliation_follows_scan_pagination(self):
        self.m.execution_table.scan.side_effect = [
            {"Items": [], "LastEvaluatedKey": {"executionKey": "cursor"}}, {"Items": []},
        ]
        self.reconcile()
        self.assertEqual(self.m.execution_table.scan.call_args.kwargs["ExclusiveStartKey"], {"executionKey": "cursor"})
        self.post.assert_not_called()

    def test_poll_stops_before_next_request_when_budget_is_exhausted(self):
        self.m._context = Mock()
        self.m._context.get_remaining_time_in_millis.side_effect = [35000, 31000]
        self.get.side_effect = None
        self.get.return_value.json.return_value = {"status": 0, "data": {"list": [{"status": "EXECUTED"}]}}
        with self.assertRaises(self.m.ExecutionBudgetExceeded):
            self.real_wait("123", attempts=1)
        self.get.assert_called_once()
        self.assertEqual(sum(self.get.call_args.kwargs["timeout"]), 5)

    def test_zero_fill_terminal_order_is_recorded_as_failed_without_resubmission(self):
        self.wait.side_effect = SimulatedLambdaTermination()
        with self.assertRaises(SimulatedLambdaTermination):
            self.m.lambda_handler({}, None)
        self.stale_record()
        self.wait.side_effect = self.real_wait
        with patch.object(self.m, "_private_get", side_effect=[
            {"list": [{"status": "CANCELED", "executedSize": "0.00000"}]}, {"list": []},
        ]):
            self.reconcile()
        self.assertEqual(next(iter(self.records.values()))["status"], "failed")
        self.assertEqual(next(iter(self.history.values()))["status"], "failed")
        self.post.assert_called_once()

    def test_reconciliation_skips_records_that_may_still_be_running(self):
        self.wait.side_effect = SimulatedLambdaTermination()
        with self.assertRaises(SimulatedLambdaTermination):
            self.m.lambda_handler({}, None)
        self.wait.reset_mock(side_effect=True)
        self.reconcile()
        self.wait.assert_not_called()
        self.assertEqual(next(iter(self.history.values()))["status"], "pending")


if __name__ == "__main__":
    unittest.main()
