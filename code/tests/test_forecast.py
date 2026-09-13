"""Tests for the code.forecast package (90-day balance projection and
amount_safe_to_pay / earliest_date_for_full_payment safety computations).

All fixtures are constructed synthetically (small in-memory DataFrames /
FinancialState instances) rather than depending on live dataset request
IDs, per Phase 2 planning decision: dataset-backed fixtures drift as
requests.csv facts get re-derived; synthetic fixtures pin down exact
expected numbers.
"""

from __future__ import annotations

import unittest

import pandas as pd

from code.forecast.balance import DailyBalance, project_balance
from code.forecast.safety import (
    compute_amount_safe_to_pay,
    compute_earliest_date_for_full_payment,
)
from code.state.reconcile import FinancialState
from code.state.recurrence import RecurrenceInfo


def _events_df(rows: list[dict]) -> pd.DataFrame:
    """Build an events DataFrame with sane defaults for columns not passed."""
    defaults = {
        "event_id": None,
        "user_id": "user_test",
        "event_type": "expense",
        "category": "misc",
        "direction": "debit",
        "amount_home_currency": 0.0,
        "event_date": pd.Timestamp("2024-01-01"),
        "settlement_date": pd.NaT,
        "status": "settled",
        "flexibility": "fixed",
        "counts_toward_forecast": True,
        "treatment": "historical",
    }
    built = []
    for row in rows:
        merged = {**defaults, **row}
        built.append(merged)
    df = pd.DataFrame(built)
    df["event_date"] = pd.to_datetime(df["event_date"])
    df["settlement_date"] = pd.to_datetime(df["settlement_date"])
    return df


class TestProjectBalance(unittest.TestCase):
    def test_recurring_rent_drops_balance_on_recurrence_date(self):
        # Last observed settled rent occurrence 2024-01-01 (30-day cadence),
        # so next occurrence lands on 2024-01-31 -- within a 90-day window
        # starting 2024-01-05.
        events = _events_df(
            [
                {
                    "event_id": "event_rent",
                    "category": "rent",
                    "direction": "debit",
                    "amount_home_currency": 5148.0,
                    "event_date": "2024-01-01",
                    "settlement_date": "2024-01-01",
                    "status": "settled",
                }
            ]
        )
        recurrence = {
            "rent": RecurrenceInfo(
                is_recurring=True,
                category="rent",
                typical_amount=5148.0,
                interval_days=30,
                occurrence_count=6,
            )
        }
        fs = FinancialState(user_id="user_test", events=events, recurrence=recurrence)

        request_date = pd.Timestamp("2024-01-05")
        proj = project_balance(fs, 10000.0, request_date, horizon_days=90)

        by_date = {d.date: d.balance for d in proj}
        recurrence_date = pd.Timestamp("2024-01-31")
        before = by_date[recurrence_date - pd.Timedelta(days=1)]
        on_date = by_date[recurrence_date]
        after = by_date[recurrence_date + pd.Timedelta(days=1)]

        self.assertAlmostEqual(before, 10000.0)
        self.assertAlmostEqual(on_date, 10000.0 - 5148.0)
        self.assertAlmostEqual(after, 10000.0 - 5148.0)

        # No invented transactions on non-recurrence days: balance should
        # only ever be 10000.0 or 10000.0 - 5148.0 (single drop) or further
        # dropped if a second occurrence also falls in-window (2024-03-01).
        distinct_balances = sorted(set(round(b, 2) for b in by_date.values()))
        self.assertLessEqual(len(distinct_balances), 3)

    def test_one_time_scheduled_debit_hits_exact_date(self):
        request_date = pd.Timestamp("2024-02-01")
        target_date = request_date + pd.Timedelta(days=10)
        events = _events_df(
            [
                {
                    "event_id": "event_onetime",
                    "category": "shopping",
                    "direction": "debit",
                    "amount_home_currency": 300.0,
                    "event_date": target_date,
                    "settlement_date": target_date,
                    "status": "scheduled",
                }
            ]
        )
        fs = FinancialState(user_id="user_test", events=events, recurrence={})
        proj = project_balance(fs, 1000.0, request_date, horizon_days=90)
        by_date = {d.date: d.balance for d in proj}

        self.assertAlmostEqual(by_date[target_date - pd.Timedelta(days=1)], 1000.0)
        self.assertAlmostEqual(by_date[target_date], 700.0)
        self.assertAlmostEqual(by_date[target_date + pd.Timedelta(days=1)], 700.0)

    def test_excluded_event_never_affects_projection(self):
        request_date = pd.Timestamp("2024-02-01")
        excluded_row = {
            "event_id": "event_excluded",
            "category": "windfall",
            "direction": "credit",
            "amount_home_currency": 99999.0,
            "event_date": request_date + pd.Timedelta(days=5),
            "settlement_date": request_date + pd.Timedelta(days=5),
            "status": "pending",
            "counts_toward_forecast": False,
            "treatment": "exclude_pending_credit",
        }

        events_without = _events_df([])
        events_with = _events_df([excluded_row])

        fs_without = FinancialState(user_id="user_test", events=events_without, recurrence={})
        fs_with = FinancialState(user_id="user_test", events=events_with, recurrence={})

        proj_without = project_balance(fs_without, 500.0, request_date, horizon_days=90)
        proj_with = project_balance(fs_with, 500.0, request_date, horizon_days=90)

        balances_without = [d.balance for d in proj_without]
        balances_with = [d.balance for d in proj_with]
        self.assertEqual(balances_without, balances_with)

    def test_returns_horizon_plus_one_entries_with_nondecreasing_dates(self):
        request_date = pd.Timestamp("2024-03-01")
        fs = FinancialState(user_id="user_test", events=_events_df([]), recurrence={})
        proj = project_balance(fs, 100.0, request_date, horizon_days=90)

        self.assertEqual(len(proj), 91)
        self.assertEqual(proj[0].date, request_date)
        self.assertEqual(proj[-1].date, request_date + pd.Timedelta(days=90))
        for i in range(1, len(proj)):
            self.assertEqual(proj[i].date - proj[i - 1].date, pd.Timedelta(days=1))


class TestComputeAmountSafeToPay(unittest.TestCase):
    def _flat_balances(self, start_date: pd.Timestamp, value: float, days: int = 90):
        return [
            DailyBalance(date=start_date + pd.Timedelta(days=i), balance=value, events_applied=[])
            for i in range(days + 1)
        ]

    def test_fully_affordable_returns_full_amount_and_request_date(self):
        start = pd.Timestamp("2024-01-01")
        balances = self._flat_balances(start, 10000.0)
        safe = compute_amount_safe_to_pay(balances, 5000.0, 2000.0)
        earliest = compute_earliest_date_for_full_payment(balances, 5000.0, 2000.0)

        self.assertAlmostEqual(safe, 5000.0)
        self.assertEqual(earliest, start)

    def test_partial_amount_when_full_would_breach_minimum(self):
        start = pd.Timestamp("2024-01-01")
        balances = self._flat_balances(start, 3000.0)
        safe = compute_amount_safe_to_pay(balances, 5000.0, 2000.0)
        earliest = compute_earliest_date_for_full_payment(balances, 5000.0, 2000.0)

        self.assertAlmostEqual(safe, 1000.0)
        self.assertIsNone(earliest)

    def test_zero_when_no_positive_amount_is_safe(self):
        start = pd.Timestamp("2024-01-01")
        balances = self._flat_balances(start, 1500.0)
        safe = compute_amount_safe_to_pay(balances, 5000.0, 2000.0)
        self.assertAlmostEqual(safe, 0.0)

    def test_earliest_full_payment_none_when_never_safe(self):
        start = pd.Timestamp("2024-01-01")
        balances = self._flat_balances(start, 100.0)
        earliest = compute_earliest_date_for_full_payment(balances, 5000.0, 2000.0)
        self.assertIsNone(earliest)

    def test_amount_safe_to_pay_never_exceeds_requested_amount(self):
        start = pd.Timestamp("2024-01-01")
        balances = self._flat_balances(start, 1_000_000.0)
        safe = compute_amount_safe_to_pay(balances, 500.0, 2000.0)
        self.assertTrue(0 <= safe <= 500.0)
        self.assertAlmostEqual(safe, 500.0)

    def test_earliest_date_after_balance_rises(self):
        start = pd.Timestamp("2024-01-01")
        balances = self._flat_balances(start, 1000.0, days=30)
        # Salary lands on day 10, pushing balance to 10000 from then on.
        for i in range(10, 31):
            balances[i] = DailyBalance(date=balances[i].date, balance=10000.0, events_applied=["event_salary"])

        earliest = compute_earliest_date_for_full_payment(balances, 5000.0, 2000.0)
        self.assertEqual(earliest, start + pd.Timedelta(days=10))


if __name__ == "__main__":
    unittest.main()
