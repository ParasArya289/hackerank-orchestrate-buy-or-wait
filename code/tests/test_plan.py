"""Tests for the code.plan package: candidate plan eligibility
determination (PLAN-01, including changes-adjusted eligibility),
recurring-flexible spending-change selection and changes-adjusted safety
recomputation (PLAN-04), and ranking/final selection with payment_plan
string building (PLAN-02/PLAN-03).

All fixtures are constructed synthetically (small in-memory Series /
DataFrames / FinancialState instances) rather than depending on live
dataset request IDs, matching Phase 2's existing test_forecast.py
convention.
"""

from __future__ import annotations

import unittest

import pandas as pd

from code.dataio.join import RequestBundle
from code.plan.eligibility import CandidatePlan, determine_eligible_plans
from code.plan.select import build_payment_plan_string, rank_plans, select_best_plan
from code.plan.spending_changes import (
    apply_spending_changes_to_state,
    recompute_safety_with_changes,
    select_spending_changes,
)
from code.state.reconcile import FinancialState
from code.state.recurrence import RecurrenceInfo


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------


def _profile(
    payment_methods_user_will_consider=None,
    max_installment_months=None,
    expense_categories_to_protect=None,
    expense_categories_user_is_willing_to_reduce=None,
    expense_categories_user_is_willing_to_stop=None,
) -> pd.Series:
    return pd.Series(
        {
            "user_id": "user_test",
            "home_currency": "USD",
            "current_available_balance": 10000.0,
            "minimum_balance_to_keep": 100.0,
            "financial_priorities": [],
            "expense_categories_to_protect": expense_categories_to_protect or [],
            "expense_categories_user_is_willing_to_reduce": expense_categories_user_is_willing_to_reduce
            or [],
            "expense_categories_user_is_willing_to_stop": expense_categories_user_is_willing_to_stop
            or [],
            "payment_methods_user_will_consider": payment_methods_user_will_consider or [],
            "max_installment_months": max_installment_months,
        }
    )


def _request(
    request_date="2024-01-01",
    desired_completion_date="2024-03-01",
    requested_amount=1000.0,
    allows_partial_payment="true",
) -> pd.Series:
    return pd.Series(
        {
            "request_id": "request_test",
            "user_id": "user_test",
            "request_date": pd.Timestamp(request_date),
            "request_type": "purchase",
            "requested_amount": requested_amount,
            "desired_completion_date": pd.Timestamp(desired_completion_date),
            "allows_partial_payment": allows_partial_payment,
            "request_text": "",
        }
    )


def _payment_options(rows: list[dict]) -> pd.DataFrame:
    defaults = {
        "payment_option_id": "payment_option_01",
        "request_id": "request_test",
        "payment_method": "installments",
        "payment_amount": 0.0,
        "number_of_payments": 1,
        "first_payment_date": pd.Timestamp("2024-01-01"),
        "payment_frequency_days": 30,
        "financing_fee": 0.0,
        "total_payable_amount": 0.0,
    }
    built = [{**defaults, **row} for row in rows]
    if not built:
        return pd.DataFrame(columns=list(defaults.keys()))
    return pd.DataFrame(built)


def _bundle(request=None, profile=None, payment_options=None) -> RequestBundle:
    return RequestBundle(
        request=request if request is not None else _request(),
        profile=profile if profile is not None else _profile(),
        events=pd.DataFrame(),
        payment_options=payment_options if payment_options is not None else _payment_options([]),
        messages=pd.DataFrame(),
        images=pd.DataFrame(),
    )


def _events_df(rows: list[dict]) -> pd.DataFrame:
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
        "minimum_allowed_amount": float("nan"),
    }
    built = [{**defaults, **row} for row in rows]
    if not built:
        return pd.DataFrame(columns=list(defaults.keys()))
    df = pd.DataFrame(built)
    df["event_date"] = pd.to_datetime(df["event_date"])
    df["settlement_date"] = pd.to_datetime(df["settlement_date"])
    return df


def _streaming_fixture_state() -> FinancialState:
    """5 settled monthly 50.00 'streaming' events including
    event_TEST_001, is_recurring=True, flexibility=stoppable, category
    permitted to stop and not protected."""
    rows = []
    for i in range(5):
        rows.append(
            {
                "event_id": f"event_TEST_00{i + 1}",
                "category": "streaming",
                "direction": "debit",
                "amount_home_currency": 50.0,
                "event_date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=30 * i),
                "settlement_date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=30 * i),
                "status": "settled",
                "flexibility": "stoppable",
            }
        )
    events = _events_df(rows)
    recurrence = {
        "streaming": RecurrenceInfo(
            is_recurring=True,
            category="streaming",
            typical_amount=50.0,
            interval_days=30,
            occurrence_count=5,
        )
    }
    return FinancialState(user_id="user_test", events=events, recurrence=recurrence)


def _streaming_fixture_profile() -> pd.Series:
    return _profile(
        payment_methods_user_will_consider=["full_payment"],
        expense_categories_user_is_willing_to_stop=["streaming"],
    )


# ---------------------------------------------------------------------------
# Task 1: eligibility.py
# ---------------------------------------------------------------------------


class TestDetermineEligiblePlans(unittest.TestCase):
    def test_full_payment_only_when_only_method_accepted_and_safe(self):
        bundle = _bundle(
            profile=_profile(payment_methods_user_will_consider=["full_payment"]),
            payment_options=_payment_options(
                [{"payment_method": "installments", "number_of_payments": 3}]
            ),
        )
        candidates = determine_eligible_plans(
            bundle, amount_safe_to_pay=1000.0, earliest_date_for_full_payment=None
        )
        methods = [c.method for c in candidates]
        self.assertIn("full_payment", methods)
        self.assertNotIn("installments", methods)
        self.assertNotIn("partial_payment", methods)
        full_payment = [c for c in candidates if c.method == "full_payment"][0]
        self.assertFalse(full_payment.requires_spending_changes)

    def test_installments_excludes_option_exceeding_max_months_includes_within(self):
        bundle = _bundle(
            profile=_profile(
                payment_methods_user_will_consider=["installments"],
                max_installment_months=6,
            ),
            payment_options=_payment_options(
                [
                    {
                        "payment_option_id": "payment_option_01",
                        "payment_method": "installments",
                        "number_of_payments": 24,
                        "payment_frequency_days": 30,
                        "payment_amount": 100.0,
                        "total_payable_amount": 2400.0,
                        "first_payment_date": pd.Timestamp("2024-01-05"),
                    },
                    {
                        "payment_option_id": "payment_option_02",
                        "payment_method": "installments",
                        "number_of_payments": 6,
                        "payment_frequency_days": 30,
                        "payment_amount": 200.0,
                        "total_payable_amount": 1200.0,
                        "first_payment_date": pd.Timestamp("2024-01-05"),
                    },
                ]
            ),
        )
        candidates = determine_eligible_plans(
            bundle, amount_safe_to_pay=0.0, earliest_date_for_full_payment=None
        )
        installment_ids = {
            c.payment_option_id for c in candidates if c.method == "installments"
        }
        self.assertNotIn("payment_option_01", installment_ids)
        self.assertIn("payment_option_02", installment_ids)

    def test_blank_max_installment_months_never_produces_installments(self):
        bundle = _bundle(
            profile=_profile(
                payment_methods_user_will_consider=["installments"],
                max_installment_months=float("nan"),
            ),
            payment_options=_payment_options(
                [{"payment_method": "installments", "number_of_payments": 3}]
            ),
        )
        candidates = determine_eligible_plans(
            bundle, amount_safe_to_pay=0.0, earliest_date_for_full_payment=None
        )
        methods = [c.method for c in candidates]
        self.assertNotIn("installments", methods)

    def test_wait_produced_when_earliest_date_present_none_when_absent(self):
        bundle = _bundle(profile=_profile(payment_methods_user_will_consider=["full_payment"]))
        future_date = pd.Timestamp("2024-02-01")
        candidates_with_wait = determine_eligible_plans(
            bundle,
            amount_safe_to_pay=500.0,
            earliest_date_for_full_payment=future_date,
        )
        self.assertIn("wait", [c.method for c in candidates_with_wait])

        candidates_without_wait = determine_eligible_plans(
            bundle, amount_safe_to_pay=500.0, earliest_date_for_full_payment=None
        )
        self.assertNotIn("wait", [c.method for c in candidates_without_wait])

    def test_not_recommended_fallback_always_present(self):
        bundle = _bundle(profile=_profile(payment_methods_user_will_consider=[]))
        candidates = determine_eligible_plans(
            bundle, amount_safe_to_pay=0.0, earliest_date_for_full_payment=None
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].method, "not_recommended")

    def test_changes_adjusted_full_payment_eligibility(self):
        bundle = _bundle(
            request=_request(requested_amount=1000.0, allows_partial_payment="false"),
            profile=_profile(payment_methods_user_will_consider=["full_payment"]),
        )

        # Raw amount_safe_to_pay alone (950.0) is not enough -- no
        # full_payment candidate without adjustment.
        candidates_raw_only = determine_eligible_plans(
            bundle,
            amount_safe_to_pay=950.0,
            earliest_date_for_full_payment=None,
            adjusted_amount_safe_to_pay=None,
        )
        self.assertNotIn("full_payment", [c.method for c in candidates_raw_only])

        # With adjusted_amount_safe_to_pay=1000.0, full_payment qualifies
        # with requires_spending_changes=True.
        candidates_adjusted = determine_eligible_plans(
            bundle,
            amount_safe_to_pay=950.0,
            earliest_date_for_full_payment=None,
            adjusted_amount_safe_to_pay=1000.0,
            adjusted_earliest_date_for_full_payment=None,
        )
        full_payment = [c for c in candidates_adjusted if c.method == "full_payment"]
        self.assertEqual(len(full_payment), 1)
        self.assertTrue(full_payment[0].requires_spending_changes)
        self.assertEqual(full_payment[0].legs, [(pd.Timestamp("2024-01-01"), 1000.0)])

    def test_partial_payment_two_legs_summing_to_requested_amount(self):
        bundle = _bundle(
            request=_request(
                requested_amount=1000.0,
                desired_completion_date="2024-03-01",
                allows_partial_payment="true",
            ),
            profile=_profile(payment_methods_user_will_consider=["partial_payment"]),
        )
        earliest = pd.Timestamp("2024-02-01")
        candidates = determine_eligible_plans(
            bundle, amount_safe_to_pay=600.0, earliest_date_for_full_payment=earliest
        )
        partial = [c for c in candidates if c.method == "partial_payment"]
        self.assertEqual(len(partial), 1)
        self.assertEqual(partial[0].legs, [(pd.Timestamp("2024-01-01"), 600.0), (earliest, 400.0)])
        self.assertAlmostEqual(sum(amount for _, amount in partial[0].legs), 1000.0)


# ---------------------------------------------------------------------------
# Task 2a: spending_changes.py
# ---------------------------------------------------------------------------


class TestSelectSpendingChanges(unittest.TestCase):
    def test_never_selects_protected_category(self):
        events = _events_df(
            [
                {
                    "event_id": "event_rent",
                    "category": "rent",
                    "flexibility": "stoppable",
                    "amount_home_currency": 500.0,
                }
                for _ in range(1)
            ]
        )
        recurrence = {
            "rent": RecurrenceInfo(
                is_recurring=True,
                category="rent",
                typical_amount=500.0,
                interval_days=30,
                occurrence_count=3,
            )
        }
        state = FinancialState(user_id="user_test", events=events, recurrence=recurrence)
        profile = _profile(
            expense_categories_to_protect=["rent"],
            expense_categories_user_is_willing_to_stop=["rent"],
        )
        actions = select_spending_changes(state, profile)
        self.assertEqual(actions, [])

    def test_never_selects_non_recurring_category(self):
        events = _events_df(
            [
                {
                    "event_id": "event_onetime",
                    "category": "entertainment",
                    "flexibility": "stoppable",
                    "amount_home_currency": 200.0,
                }
            ]
        )
        # entertainment not in recurrence dict at all -- not recurring.
        state = FinancialState(user_id="user_test", events=events, recurrence={})
        profile = _profile(expense_categories_user_is_willing_to_stop=["entertainment"])
        actions = select_spending_changes(state, profile)
        self.assertEqual(actions, [])

    def test_never_emits_both_stop_and_reduce_for_same_event(self):
        state = _streaming_fixture_state()
        # Make the representative row reducible_or_stoppable and permit both.
        state.events.loc[state.events["event_id"] == "event_TEST_005", "flexibility"] = (
            "reducible_or_stoppable"
        )
        profile = _profile(
            payment_methods_user_will_consider=["full_payment"],
            expense_categories_user_is_willing_to_stop=["streaming"],
            expense_categories_user_is_willing_to_reduce=["streaming"],
        )
        actions = select_spending_changes(state, profile)
        event_ids_seen = set()
        for action in actions:
            if action.startswith("stop:"):
                event_ids_seen.add(action[len("stop:") :])
            else:
                event_id = action[len("reduce_to:") :].rsplit(":", 1)[0]
                event_ids_seen.add(event_id)
        # No event_id should appear more than once across the returned list.
        self.assertEqual(len(actions), len(event_ids_seen))

    def test_returns_at_most_three_actions(self):
        rows = []
        recurrence = {}
        categories = ["cat_a", "cat_b", "cat_c", "cat_d"]
        for cat in categories:
            for i in range(3):
                rows.append(
                    {
                        "event_id": f"event_{cat}_{i}",
                        "category": cat,
                        "flexibility": "stoppable",
                        "amount_home_currency": 50.0 + categories.index(cat),
                        "event_date": pd.Timestamp("2024-01-01") + pd.Timedelta(days=30 * i),
                    }
                )
            recurrence[cat] = RecurrenceInfo(
                is_recurring=True,
                category=cat,
                typical_amount=50.0,
                interval_days=30,
                occurrence_count=3,
            )
        events = _events_df(rows)
        state = FinancialState(user_id="user_test", events=events, recurrence=recurrence)
        profile = _profile(expense_categories_user_is_willing_to_stop=categories)
        actions = select_spending_changes(state, profile)
        self.assertLessEqual(len(actions), 3)

    def test_synthetic_fixture_returns_stop_event_test_001(self):
        state = _streaming_fixture_state()
        profile = _streaming_fixture_profile()
        actions = select_spending_changes(state, profile)
        self.assertEqual(actions, ["stop:event_TEST_005"])


class TestRecomputeSafetyWithChanges(unittest.TestCase):
    def test_synthetic_fixture_raises_adjusted_safe_amount(self):
        state = _streaming_fixture_state()
        request_date = pd.Timestamp("2024-04-01")

        # Raw projection (no changes): the streaming category still
        # projects its recurring 50.0 debits forward within the 90-day
        # horizon, reducing the minimum projected balance (and therefore
        # amount_safe_to_pay) versus the changes-adjusted projection
        # where those debits are stopped.
        from code.forecast.balance import project_balance
        from code.forecast.safety import compute_amount_safe_to_pay

        starting_balance = 1000.0
        minimum_balance_to_keep = 0.0
        requested_amount = 1000.0

        raw_daily_balances = project_balance(state, starting_balance, request_date, horizon_days=90)
        raw_safe = compute_amount_safe_to_pay(
            raw_daily_balances, requested_amount, minimum_balance_to_keep
        )

        adjusted_safe, _ = recompute_safety_with_changes(
            state,
            ["stop:event_TEST_005"],
            starting_balance,
            request_date,
            requested_amount,
            minimum_balance_to_keep,
            horizon_days=90,
        )
        # Stopping the streaming category removes it from
        # project_balance's recurring-projection set, freeing the
        # headroom from every *projected* future occurrence (only the
        # concrete historical event_TEST_005 row, already inside the
        # window as a one-time event, still applies once). The adjusted
        # safe amount is strictly higher than the raw (unchanged)
        # projection's safe amount.
        self.assertGreater(adjusted_safe, raw_safe)

    def test_empty_actions_returns_none_none(self):
        state = _streaming_fixture_state()
        result = recompute_safety_with_changes(
            state, [], 1000.0, pd.Timestamp("2024-04-01"), 1000.0, 0.0
        )
        self.assertEqual(result, (None, None))


class TestApplySpendingChangesToState(unittest.TestCase):
    def test_stop_action_does_not_mutate_original_recurrence(self):
        state = _streaming_fixture_state()
        original_is_recurring = state.recurrence["streaming"].is_recurring
        patched = apply_spending_changes_to_state(state, ["stop:event_TEST_005"])
        self.assertFalse(patched.recurrence["streaming"].is_recurring)
        # Original untouched.
        self.assertEqual(state.recurrence["streaming"].is_recurring, original_is_recurring)
        self.assertTrue(state.recurrence["streaming"].is_recurring)


# ---------------------------------------------------------------------------
# Task 2b: select.py
# ---------------------------------------------------------------------------


def _candidate(**kwargs) -> CandidatePlan:
    defaults = dict(
        method="installments",
        payment_option_id=None,
        legs=[],
        total_paid=0.0,
        completes_by_deadline=True,
        requires_spending_changes=False,
        start_date=pd.Timestamp("2024-01-01"),
        num_payments=1,
    )
    return CandidatePlan(**{**defaults, **kwargs})


class TestRankPlans(unittest.TestCase):
    def test_deadline_completion_wins_over_all_else(self):
        misses_deadline = _candidate(
            method="installments", completes_by_deadline=False, total_paid=100.0
        )
        meets_deadline = _candidate(
            method="installments", completes_by_deadline=True, total_paid=99999.0
        )
        ranked = rank_plans([misses_deadline, meets_deadline])
        self.assertIs(ranked[0], meets_deadline)

    def test_requires_no_spending_changes_wins_tiebreak(self):
        needs_changes = _candidate(
            method="full_payment", requires_spending_changes=True, total_paid=100.0
        )
        no_changes = _candidate(
            method="full_payment", requires_spending_changes=False, total_paid=100.0
        )
        ranked = rank_plans([needs_changes, no_changes])
        self.assertIs(ranked[0], no_changes)

    def test_full_tiebreak_chain(self):
        # Both complete by deadline, neither requires changes.
        cheaper = _candidate(
            method="installments",
            payment_option_id="payment_option_09",
            total_paid=100.0,
            start_date=pd.Timestamp("2024-01-01"),
            num_payments=6,
        )
        pricier = _candidate(
            method="installments",
            payment_option_id="payment_option_01",
            total_paid=200.0,
            start_date=pd.Timestamp("2024-01-01"),
            num_payments=6,
        )
        ranked = rank_plans([pricier, cheaper])
        self.assertIs(ranked[0], cheaper)  # rule 3: lower total_paid wins

        later = _candidate(
            method="installments",
            payment_option_id="payment_option_09",
            total_paid=100.0,
            start_date=pd.Timestamp("2024-02-01"),
            num_payments=6,
        )
        earlier = _candidate(
            method="installments",
            payment_option_id="payment_option_09",
            total_paid=100.0,
            start_date=pd.Timestamp("2024-01-01"),
            num_payments=6,
        )
        ranked = rank_plans([later, earlier])
        self.assertIs(ranked[0], earlier)  # rule 4: earlier start_date wins

        more_payments = _candidate(
            method="installments",
            payment_option_id="payment_option_09",
            total_paid=100.0,
            start_date=pd.Timestamp("2024-01-01"),
            num_payments=12,
        )
        fewer_payments = _candidate(
            method="installments",
            payment_option_id="payment_option_09",
            total_paid=100.0,
            start_date=pd.Timestamp("2024-01-01"),
            num_payments=6,
        )
        ranked = rank_plans([more_payments, fewer_payments])
        self.assertIs(ranked[0], fewer_payments)  # rule 5: fewer payments wins

        higher_id = _candidate(
            method="installments",
            payment_option_id="payment_option_07",
            total_paid=100.0,
            start_date=pd.Timestamp("2024-01-01"),
            num_payments=6,
        )
        lower_id = _candidate(
            method="installments",
            payment_option_id="payment_option_05",
            total_paid=100.0,
            start_date=pd.Timestamp("2024-01-01"),
            num_payments=6,
        )
        ranked = rank_plans([higher_id, lower_id])
        self.assertIs(ranked[0], lower_id)  # rule 6: lower payment_option_id wins

    def test_select_best_plan_returns_top_ranked(self):
        worse = _candidate(method="installments", completes_by_deadline=False)
        better = _candidate(method="installments", completes_by_deadline=True)
        self.assertIs(select_best_plan([worse, better]), better)

    def test_not_recommended_only_chosen_when_sole_candidate(self):
        fallback = _candidate(method="not_recommended", legs=[], completes_by_deadline=False)
        real = _candidate(method="full_payment", completes_by_deadline=True)
        self.assertIs(select_best_plan([fallback, real]), real)
        self.assertIs(select_best_plan([fallback]), fallback)


class TestBuildPaymentPlanString(unittest.TestCase):
    def test_none_for_empty_legs(self):
        candidate = _candidate(legs=[])
        self.assertEqual(build_payment_plan_string(candidate), "none")

    def test_whole_number_amount_no_trailing_zero(self):
        candidate = _candidate(legs=[(pd.Timestamp("2024-03-03"), 25256.0)])
        self.assertEqual(build_payment_plan_string(candidate), "2024-03-03:25256")

    def test_matches_sample_requests_request_02_style(self):
        candidate = _candidate(
            legs=[
                (pd.Timestamp("2025-08-08"), 15952906.67),
                (pd.Timestamp("2025-09-07"), 15952906.67),
                (pd.Timestamp("2025-10-07"), 15952906.67),
            ]
        )
        self.assertEqual(
            build_payment_plan_string(candidate),
            "2025-08-08:15952906.67|2025-09-07:15952906.67|2025-10-07:15952906.67",
        )

    def test_raises_value_error_on_non_chronological_legs(self):
        candidate = _candidate(
            legs=[(pd.Timestamp("2024-02-01"), 100.0), (pd.Timestamp("2024-01-01"), 200.0)]
        )
        with self.assertRaises(ValueError):
            build_payment_plan_string(candidate)


if __name__ == "__main__":
    unittest.main()
