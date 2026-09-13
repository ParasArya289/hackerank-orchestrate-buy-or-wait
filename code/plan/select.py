"""Ranking and final plan selection (PLAN-02 / PLAN-03).

rank_plans implements the exact 6-step precedence from
problem_statement.md "Choosing Between Safe Plans" (verbatim order):
    1. completes the full request by desired_completion_date
    2. requires no spending changes
    3. minimizes total amount paid
    4. starts payment earlier
    5. uses fewer payments
    6. lowest payment_option_id as final tie-break

select_best_plan returns the single top-ranked candidate (or the sole
not_recommended fallback if that is all there is).

build_payment_plan_string renders a CandidatePlan's legs in the
sample_requests.csv "YYYY-MM-DD:amount" | "YYYY-MM-DD:amount" style.
"""

from __future__ import annotations

import re

import pandas as pd


def _payment_option_sort_key(payment_option_id) -> float:
    """Lower sorts first. None (full_payment/partial_payment/wait/
    not_recommended never carry a payment_option_id) sorts last so it
    never wins a tie-break against a real installments option on this
    axis alone."""
    if payment_option_id is None:
        return float("inf")
    match = re.search(r"(\d+)$", str(payment_option_id))
    if match:
        return float(int(match.group(1)))
    return float("inf")


def _rank_key(candidate):
    return (
        not candidate.completes_by_deadline,
        candidate.requires_spending_changes,
        candidate.total_paid,
        candidate.start_date,
        candidate.num_payments,
        _payment_option_sort_key(candidate.payment_option_id),
    )


def rank_plans(candidates: list) -> list:
    """Return `candidates` sorted best-first by the 6-step precedence.
    Excludes the not_recommended fallback unless it is the only
    candidate."""
    if len(candidates) > 1:
        rankable = [c for c in candidates if c.method != "not_recommended"]
    else:
        rankable = list(candidates)
    if not rankable:
        rankable = list(candidates)
    return sorted(rankable, key=_rank_key)


def select_best_plan(candidates: list):
    """Return the single top-ranked CandidatePlan."""
    return rank_plans(candidates)[0]


def _format_amount(amount: float) -> str:
    """Format without unnecessary trailing .0 for whole numbers, but
    preserve up to 2 decimal places otherwise. Never uses scientific
    notation (rules out `:g`, which switches to exponent form for large
    magnitudes such as 15952906.67)."""
    rounded = round(amount, 2)
    if rounded == int(rounded):
        return f"{int(rounded)}"
    text = f"{rounded:.2f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def build_payment_plan_string(candidate_plan) -> str:
    """Render candidate_plan.legs as 'YYYY-MM-DD:amount' entries joined
    by '|', or the literal string 'none' for an empty legs list."""
    legs = candidate_plan.legs
    if not legs:
        return "none"

    for i in range(len(legs) - 1):
        if legs[i][0] > legs[i + 1][0]:
            raise ValueError("CandidatePlan.legs must be in chronological order")

    parts = []
    for date, amount in legs:
        timestamp = pd.Timestamp(date)
        parts.append(f"{timestamp.strftime('%Y-%m-%d')}:{_format_amount(amount)}")
    return "|".join(parts)
