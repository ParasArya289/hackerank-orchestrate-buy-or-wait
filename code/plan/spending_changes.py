"""Recurring-flexible spending-change selection and changes-adjusted
safety recomputation (PLAN-04).

Per problem_statement.md "Choosing Between Safe Plans" verbatim: "Only
recurring expenses marked as flexible may be changed." This module never
selects a protected-category event (protection overrides flexibility
unconditionally), never selects a non-recurring category's event (a
one-time flexible purchase is never eligible regardless of its
flexibility label), and never emits both a stop and a reduce action for
the same event_id.

apply_spending_changes_to_state / recompute_safety_with_changes reuse
Plan 01's project_balance / compute_amount_safe_to_pay /
compute_earliest_date_for_full_payment directly -- the changes-adjusted
numbers are produced by the exact same trusted algorithm as the raw
numbers, just against a patched FinancialState.recurrence, and the
original FinancialState is never mutated in place (threat model
T-02-10).
"""

from __future__ import annotations

import copy

import pandas as pd

from code.forecast.balance import project_balance
from code.forecast.safety import (
    compute_amount_safe_to_pay,
    compute_earliest_date_for_full_payment,
)
from code.state.reconcile import FinancialState


def _eligible_candidate_rows(financial_state: FinancialState, profile) -> "pd.DataFrame":
    events = financial_state.events
    protect = set(profile["expense_categories_to_protect"])

    mask = (
        (events["counts_toward_forecast"] == True)  # noqa: E712
        & (~events["category"].isin(protect))
        & (events["flexibility"].isin(["stoppable", "reducible", "reducible_or_stoppable"]))
    )
    candidates = events[mask].copy()
    if len(candidates) == 0:
        return candidates

    def _is_recurring(category) -> bool:
        info = financial_state.recurrence.get(category)
        return info is not None and info.is_recurring is True

    candidates = candidates[candidates["category"].apply(_is_recurring)]
    return candidates


def select_spending_changes(financial_state: FinancialState, profile, max_actions: int = 3) -> list:
    """Return at most `max_actions` action strings (`stop:<event_id>` or
    `reduce_to:<event_id>:<new_amount>`) drawn from non-protected,
    recurring, flexible, user-permitted-category events. One action per
    eligible category (the single most-recent-event_date row represents
    that category's forward-looking action). Never emits both a stop and
    a reduce for the same event_id -- stop is preferred when an event
    qualifies for both. Returns [] when no eligible candidates exist."""
    candidates = _eligible_candidate_rows(financial_state, profile)
    if len(candidates) == 0:
        return []

    stoppable_categories = set(profile["expense_categories_user_is_willing_to_stop"])
    reducible_categories = set(profile["expense_categories_user_is_willing_to_reduce"])

    actions_with_impact = []

    for category, group in candidates.groupby("category"):
        representative = group.sort_values("event_date").iloc[-1]
        flexibility = representative["flexibility"]
        amount = float(representative["amount_home_currency"])
        event_id = representative["event_id"]

        can_stop = (
            flexibility in ("stoppable", "reducible_or_stoppable")
            and category in stoppable_categories
        )
        can_reduce = (
            flexibility in ("reducible", "reducible_or_stoppable")
            and category in reducible_categories
        )

        if can_stop:
            actions_with_impact.append((amount, f"stop:{event_id}"))
        elif can_reduce:
            minimum_allowed = representative.get("minimum_allowed_amount")
            if minimum_allowed is not None and not pd.isna(minimum_allowed):
                new_amount = float(minimum_allowed)
            else:
                new_amount = round(amount * 0.5, 2)
            actions_with_impact.append((amount, f"reduce_to:{event_id}:{new_amount}"))

    actions_with_impact.sort(key=lambda pair: pair[0], reverse=True)
    return [action for _, action in actions_with_impact[:max_actions]]


def apply_spending_changes_to_state(financial_state: FinancialState, actions: list) -> FinancialState:
    """Return a new FinancialState with `recurrence` patched to simulate
    the effect of `actions`. Never mutates the input FinancialState's
    recurrence dict in place."""
    events = financial_state.events
    patched_recurrence = copy.deepcopy(financial_state.recurrence)

    for action in actions:
        if action.startswith("stop:"):
            event_id = action[len("stop:") :]
            matches = events[events["event_id"] == event_id]
            if len(matches) == 0:
                continue
            category = matches.iloc[0]["category"]
            if category in patched_recurrence:
                patched_recurrence[category].is_recurring = False
        elif action.startswith("reduce_to:"):
            remainder = action[len("reduce_to:") :]
            event_id, new_amount_str = remainder.rsplit(":", 1)
            matches = events[events["event_id"] == event_id]
            if len(matches) == 0:
                continue
            category = matches.iloc[0]["category"]
            if category in patched_recurrence:
                patched_recurrence[category].typical_amount = float(new_amount_str)

    return FinancialState(
        user_id=financial_state.user_id,
        events=events,
        recurrence=patched_recurrence,
        amendments_applied=financial_state.amendments_applied,
    )


def recompute_safety_with_changes(
    financial_state: FinancialState,
    actions: list,
    starting_balance: float,
    request_date,
    requested_amount: float,
    minimum_balance_to_keep: float,
    horizon_days: int = 90,
):
    """Recompute amount_safe_to_pay / earliest_date_for_full_payment
    against a spending-changes-adjusted FinancialState. Returns
    (None, None) when `actions` is empty (no adjustment attempted)."""
    if not actions:
        return None, None

    patched_state = apply_spending_changes_to_state(financial_state, actions)
    adjusted_daily_balances = project_balance(
        patched_state, starting_balance, request_date, horizon_days
    )
    adjusted_amount_safe_to_pay = compute_amount_safe_to_pay(
        adjusted_daily_balances, requested_amount, minimum_balance_to_keep
    )
    adjusted_earliest_date_for_full_payment = compute_earliest_date_for_full_payment(
        adjusted_daily_balances, requested_amount, minimum_balance_to_keep
    )
    return adjusted_amount_safe_to_pay, adjusted_earliest_date_for_full_payment
