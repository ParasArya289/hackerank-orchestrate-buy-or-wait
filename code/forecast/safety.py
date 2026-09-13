"""amount_safe_to_pay and earliest_date_for_full_payment computation.

Both functions are pure over a list[DailyBalance] (the output of
code.forecast.balance.project_balance) and never re-derive the
projection themselves. Per AGENTS.md "the balance must never fall below
minimum_balance_to_keep after any projected essential expense or payment
in the recommended plan" -- minimum_balance_to_keep is treated as a hard
floor (>=, not >) in both functions.

This module computes the BASELINE forecast only -- no spending-changes
logic (that is Plan 02's job, PLAN-04) and no desired_completion_date
enforcement (also Plan 02's job).
"""

from __future__ import annotations

import math

import pandas as pd

from .balance import DailyBalance


def compute_amount_safe_to_pay(
    daily_balances: list[DailyBalance],
    requested_amount: float,
    minimum_balance_to_keep: float,
) -> float:
    """Largest amount payable on daily_balances[0].date that never drops
    the projected balance below minimum_balance_to_keep on any day in the
    window, capped at requested_amount.

    The payment is a one-time subtraction applied on day 0 that
    permanently reduces every subsequent day's balance (it is never
    repaid), so the maximum safe X equals the minimum projected balance
    across the whole horizon, minus minimum_balance_to_keep.
    """
    if not daily_balances:
        return 0.0

    min_balance = min(d.balance for d in daily_balances)
    safe_amount = min_balance - minimum_balance_to_keep

    safe_amount = max(0.0, safe_amount)
    safe_amount = min(safe_amount, requested_amount)

    # Round down to 2 decimal places to avoid a floating-point rounding
    # error producing an unsafe over-payment.
    return math.floor(safe_amount * 100) / 100


def compute_earliest_date_for_full_payment(
    daily_balances: list[DailyBalance],
    requested_amount: float,
    minimum_balance_to_keep: float,
) -> "pd.Timestamp | None":
    """First date d in daily_balances (chronological) such that paying
    requested_amount on d keeps every day from d through the end of the
    horizon >= minimum_balance_to_keep. Returns None if no such date
    exists within the horizon."""
    n = len(daily_balances)
    for start_index in range(n):
        safe = True
        for j in range(start_index, n):
            if daily_balances[j].balance - requested_amount < minimum_balance_to_keep:
                safe = False
                break
        if safe:
            return daily_balances[start_index].date
    return None
