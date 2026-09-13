"""Tests for code.output.assemble: derive_affordability_status and
build_output_row (Phase 2 Plan 03).

Tests 1-4 exercise derive_affordability_status directly against
synthetic CandidatePlan instances. Test 5 exercises the
requires_spending_changes-aware full_payment branch. Test 6 runs
build_output_row against a live dataset request_id (request_113,
confirmed requested_amount=36500 INR per Phase 1 session facts). Test 7
runs build_output_row end-to-end against the synthetic
streaming-category fixture that exercises the changes-adjusted
eligibility mechanism (dataset/sample_requests.csv request_06's general
mechanism, per the plan's Known Divergence note -- request_06's own
specific numbers are not asserted here).
"""

from __future__ import annotations

import unittest

import pandas as pd

from code.dataio.join import RequestBundle
from code.output.assemble import build_output_row, derive_affordability_status
from code.plan.eligibility import CandidatePlan
from code.state.reconcile import FinancialState
from code.state.recurrence import RecurrenceInfo


def _candidate(**kwargs) -> CandidatePlan:
    defaults = dict(
        method="full_payment",
        payment_option_id=None,
        legs=[(pd.Timestamp("2024-01-01"), 1000.0)],
        total_paid=1000.0,
        completes_by_deadline=True,
        requires_spending_changes=False,
        start_date=pd.Timestamp("2024-01-01"),
        num_payments=1,
    )
    return CandidatePlan(**{**defaults, **kwargs})


class TestDeriveAffordabilityStatus(unittest.TestCase):
    def test_full_payment_no_changes_is_affordable_now(self):
        plan = _candidate(
            method="full_payment", completes_by_deadline=True, requires_spending_changes=False
        )
        status = derive_affordability_status(plan, amount_safe_to_pay=1000.0, requested_amount=1000.0)
        self.assertEqual(status, "affordable_now")

    def test_installments_or_partial_payment_is_affordable_with_plan(self):
        installments_plan = _candidate(method="installments")
        status = derive_affordability_status(
            installments_plan, amount_safe_to_pay=1000.0, requested_amount=1000.0
        )
        self.assertEqual(status, "affordable_with_plan")

        partial_plan = _candidate(method="partial_payment")
        status = derive_affordability_status(
            partial_plan, amount_safe_to_pay=600.0, requested_amount=1000.0
        )
        self.assertEqual(status, "affordable_with_plan")

    def test_wait_is_affordable_later(self):
        plan = _candidate(method="wait")
        status = derive_affordability_status(plan, amount_safe_to_pay=0.0, requested_amount=1000.0)
        self.assertEqual(status, "affordable_later")

    def test_not_recommended_is_not_affordable(self):
        plan = _candidate(method="not_recommended", legs=[], completes_by_deadline=False)
        status = derive_affordability_status(plan, amount_safe_to_pay=0.0, requested_amount=1000.0)
        self.assertEqual(status, "not_affordable")

    def test_full_payment_requires_spending_changes_is_affordable_with_plan(self):
        plan = _candidate(
            method="full_payment", completes_by_deadline=True, requires_spending_changes=True
        )
        status = derive_affordability_status(plan, amount_safe_to_pay=950.0, requested_amount=1000.0)
        self.assertEqual(status, "affordable_with_plan")
        self.assertNotEqual(status, "affordable_now")


class TestBuildOutputRowLiveDataset(unittest.TestCase):
    def test_request_113_all_keys_populated_and_invariants_hold(self):
        row = build_output_row("request_113")
        self.assertEqual(
            list(row.keys()),
            [
                "request_id",
                "amount_safe_to_pay",
                "affordability_status",
                "recommended_payment_method",
                "payment_plan",
                "earliest_date_for_full_payment",
                "spending_changes_needed",
                "decision_explanation",
            ],
        )
        self.assertEqual(row["request_id"], "request_113")
        self.assertGreaterEqual(row["amount_safe_to_pay"], 0.0)
        self.assertLessEqual(row["amount_safe_to_pay"], 36500.0)
        self.assertIn(
            row["affordability_status"],
            {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"},
        )
        self.assertIn(
            row["recommended_payment_method"],
            {"full_payment", "partial_payment", "installments", "wait", "not_recommended"},
        )
        for key, value in row.items():
            self.assertIsNotNone(value, f"{key} must not be None")
        self.assertIsInstance(row["decision_explanation"], str)
        self.assertNotEqual(row["decision_explanation"], "")
        if row["affordability_status"] == "affordable_now":
            from code.dataio.join import build_request_bundle

            bundle = build_request_bundle("request_113")
            expected_date = pd.Timestamp(bundle.request["request_date"]).strftime("%Y-%m-%d")
            self.assertEqual(row["earliest_date_for_full_payment"], expected_date)
        if row["affordability_status"] == "not_affordable":
            self.assertEqual(row["payment_plan"], "none")
            self.assertEqual(row["earliest_date_for_full_payment"], "")


def _synthetic_tables():
    """A minimal in-memory `tables` dict for a synthetic request that
    exercises the changes-adjusted full_payment eligibility mechanism:
    requested_amount=1000.0, raw amount_safe_to_pay=950.0 (via a
    starting_balance/minimum_balance_to_keep pairing that produces exactly
    that raw safe amount), a streaming-category recurring stoppable
    event_TEST_001..005 series (only event_TEST_001 is asserted in the
    spending_changes_needed output per the plan's synthetic fixture
    description), allows_partial_payment=False so partial_payment never
    competes, and payment_methods_user_will_consider=['full_payment'] so
    only full_payment/wait/not_recommended can ever be selected.
    """
    user_id = "user_SYN"
    request_id = "request_SYN"
    request_date = pd.Timestamp("2024-04-01")
    desired_completion_date = pd.Timestamp("2024-06-01")

    requests_df = pd.DataFrame(
        [
            {
                "request_id": request_id,
                "user_id": user_id,
                "request_date": request_date,
                "request_type": "purchase",
                "requested_amount": 1000.0,
                "desired_completion_date": desired_completion_date,
                "allows_partial_payment": "false",
                "request_text": "",
            }
        ]
    )

    profiles_df = pd.DataFrame(
        [
            {
                "user_id": user_id,
                "home_currency": "USD",
                "current_available_balance": 1050.0,
                "minimum_balance_to_keep": 0.0,
                "financial_priorities": [],
                "expense_categories_to_protect": [],
                "expense_categories_user_is_willing_to_reduce": [],
                "expense_categories_user_is_willing_to_stop": ["streaming"],
                "payment_methods_user_will_consider": ["full_payment"],
                "max_installment_months": float("nan"),
            }
        ]
    )

    # 5 settled monthly 50.00 streaming debits ending just before
    # request_date so the recurring projection continues forward inside
    # the 90-day horizon. Two future occurrences (2024-05-30, 2024-06-29)
    # land within the 90-day horizon ending 2024-06-30, each subtracting
    # 50.0 from the running balance. With
    # current_available_balance=1050.0 and minimum_balance_to_keep=0.0,
    # the minimum projected balance across the horizon is
    # 1050.0 - 100.0 = 950.0, so raw amount_safe_to_pay ==
    # min_balance - minimum_balance_to_keep == 950.0 exactly (still below
    # requested_amount=1000.0, so full_payment is not raw-safe and only
    # qualifies via the changes-adjusted branch once the streaming
    # category is stopped).
    event_rows = []
    for i in range(5):
        event_rows.append(
            {
                "event_id": f"event_TEST_{i + 1:03d}",
                "user_id": user_id,
                "event_type": "expense",
                "category": "streaming",
                "amount": 50.0,
                "currency": "USD",
                "direction": "debit",
                "event_date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=30 * i),
                "settlement_date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=30 * i),
                "status": "settled",
                "flexibility": "stoppable",
                "minimum_allowed_amount": float("nan"),
            }
        )
    events_df = pd.DataFrame(event_rows)

    payment_options_df = pd.DataFrame(
        columns=[
            "payment_option_id",
            "request_id",
            "payment_method",
            "payment_amount",
            "number_of_payments",
            "first_payment_date",
            "payment_frequency_days",
            "financing_fee",
            "total_payable_amount",
        ]
    )

    exchange_rates_df = pd.DataFrame(
        columns=["from_currency", "to_currency", "rate_date", "rate"]
    )

    messages_df = pd.DataFrame(
        columns=["message_id", "user_id", "request_id", "sent_at", "source_type", "related_event_id", "message_text"]
    )
    images_df = pd.DataFrame(
        columns=["image_id", "user_id", "request_id", "related_event_id"]
    )

    return {
        "requests": requests_df,
        "profiles": profiles_df,
        "events": events_df,
        "payment_options": payment_options_df,
        "exchange_rates": exchange_rates_df,
        "messages": messages_df,
        "images": images_df,
    }


class TestBuildOutputRowNotAffordableEmptyDate(unittest.TestCase):
    def test_not_affordable_forces_empty_earliest_date_even_if_raw_date_exists(self):
        """Regression test (Rule 1 fix): a raw earliest_date_for_full_payment
        can exist (full_payment would eventually be safe in isolation) while
        the selected plan is still not_recommended, e.g. because the user's
        profile does not accept full_payment as a payment method at all. In
        that case affordability_status is not_affordable and
        earliest_date_for_full_payment must be the empty string, never the
        raw date -- per the plan's must_haves truth "not_affordable/
        never-safe implies earliest_date_for_full_payment is empty"."""
        tables = _synthetic_tables()
        # Force the profile to accept nothing usable: no full_payment, no
        # partial_payment (allows_partial_payment is already "false" in
        # the fixture), no installments (no payment options supplied) --
        # so determine_eligible_plans can only ever return the
        # not_recommended fallback, even though a raw
        # earliest_date_for_full_payment may exist in isolation.
        tables["profiles"].at[0, "payment_methods_user_will_consider"] = []
        row = build_output_row("request_SYN", tables=tables)
        self.assertEqual(row["affordability_status"], "not_affordable")
        self.assertEqual(row["recommended_payment_method"], "not_recommended")
        self.assertEqual(row["payment_plan"], "none")
        self.assertEqual(row["earliest_date_for_full_payment"], "")


class TestBuildOutputRowSyntheticFixture(unittest.TestCase):
    def test_synthetic_fixture_full_pipeline(self):
        tables = _synthetic_tables()
        row = build_output_row("request_SYN", tables=tables)

        self.assertAlmostEqual(row["amount_safe_to_pay"], 950.0, places=2)
        self.assertEqual(row["affordability_status"], "affordable_with_plan")
        self.assertEqual(row["recommended_payment_method"], "full_payment")
        self.assertTrue(row["payment_plan"].startswith("2024-04-01:1000"))
        self.assertIn("stop:event_TEST_005", row["spending_changes_needed"])


if __name__ == "__main__":
    unittest.main()
