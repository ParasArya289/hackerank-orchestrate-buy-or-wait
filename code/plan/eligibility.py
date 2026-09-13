"""Candidate plan eligibility determination (PLAN-01).

determine_eligible_plans(bundle, amount_safe_to_pay, earliest_date_for_full_payment,
adjusted_amount_safe_to_pay=None, adjusted_earliest_date_for_full_payment=None)
turns a request's forecast results (Plan 01's amount_safe_to_pay /
earliest_date_for_full_payment, both raw and, optionally, changes-adjusted
per code/plan/spending_changes.py's recompute_safety_with_changes) plus the
user's payment preferences (RequestBundle.profile) and the request's
supplied payment options (RequestBundle.payment_options) into every
eligible CandidatePlan.

Eligibility rules (problem_statement.md "Choosing Between Safe Plans",
verbatim, and this plan's Dataset Facts):
  - full_payment / partial_payment / installments (immediate methods)
    require membership in profile.payment_methods_user_will_consider.
  - installments additionally requires profile.max_installment_months to
    be non-null AND the candidate payment option's number_of_payments
    (converted to months) to not exceed max_installment_months.
  - wait requires earliest_date_for_full_payment to be non-null (full
    payment becomes safe later) AND full_payment is an accepted method.
  - not_recommended is the unconditional fallback -- always present in
    the returned list so select_best_plan never receives an empty list.

Changes-adjusted eligibility: a full_payment candidate that is not safe
under the raw amount_safe_to_pay may still qualify if a simulated
spending change (code/plan/spending_changes.py) raises the adjusted
amount_safe_to_pay to cover requested_amount. Such a candidate is added
with requires_spending_changes=True and is never added twice (raw-safe
strictly dominates adjusted-safe, so the adjusted branch only fires when
the raw branch did not already produce that method).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

_EPSILON = 1e-6


@dataclass
class CandidatePlan:
    method: str  # full_payment | partial_payment | installments | wait | not_recommended
    payment_option_id: "str | None"
    legs: list  # list[tuple[pd.Timestamp, float]] in chronological order
    total_paid: float
    completes_by_deadline: bool
    requires_spending_changes: bool
    start_date: "pd.Timestamp | None"
    num_payments: int


def _as_bool(value) -> bool:
    """Cast requests.csv's allows_partial_payment string ('true'/'false')
    to a real bool. Also tolerates an already-bool value."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() == "true"


def _build_full_payment_and_wait(
    candidates: list[CandidatePlan],
    profile,
    request_date: pd.Timestamp,
    desired_completion_date: pd.Timestamp,
    requested_amount: float,
    safe_amount,
    earliest_date,
    requires_changes: bool,
) -> None:
    """Append a full_payment CandidatePlan (in-place onto `candidates`) if
    `safe_amount` covers `requested_amount`. Mutates `candidates`."""
    if "full_payment" not in profile["payment_methods_user_will_consider"]:
        return
    if safe_amount is None:
        return
    if safe_amount >= requested_amount - _EPSILON:
        candidates.append(
            CandidatePlan(
                method="full_payment",
                payment_option_id=None,
                legs=[(request_date, requested_amount)],
                total_paid=requested_amount,
                completes_by_deadline=(request_date <= desired_completion_date),
                requires_spending_changes=requires_changes,
                start_date=request_date,
                num_payments=1,
            )
        )


def determine_eligible_plans(
    bundle,
    amount_safe_to_pay: float,
    earliest_date_for_full_payment,
    adjusted_amount_safe_to_pay: "float | None" = None,
    adjusted_earliest_date_for_full_payment=None,
) -> list:
    """Return every eligible CandidatePlan for this request, plus an
    always-present not_recommended fallback.

    bundle: a code.dataio.join.RequestBundle (request/profile/payment_options).
    amount_safe_to_pay / earliest_date_for_full_payment: raw (pre-changes)
        safety results from code.forecast.safety.
    adjusted_amount_safe_to_pay / adjusted_earliest_date_for_full_payment:
        changes-adjusted safety results from
        code.plan.spending_changes.recompute_safety_with_changes, or None
        when no spending-change candidates exist for this request.
    """
    profile = bundle.profile
    request = bundle.request

    request_date = pd.Timestamp(request["request_date"]).normalize()
    desired_completion_date = pd.Timestamp(request["desired_completion_date"]).normalize()
    requested_amount = float(request["requested_amount"])
    allows_partial_payment = _as_bool(request.get("allows_partial_payment"))

    payment_methods_user_will_consider = profile["payment_methods_user_will_consider"]
    max_installment_months = profile.get("max_installment_months")

    candidates: list[CandidatePlan] = []

    # (1) full_payment: try raw first; only try adjusted if raw did not
    # already qualify (raw-safe strictly dominates adjusted-safe).
    full_payment_before = len(candidates)
    _build_full_payment_and_wait(
        candidates,
        profile,
        request_date,
        desired_completion_date,
        requested_amount,
        amount_safe_to_pay,
        earliest_date_for_full_payment,
        requires_changes=False,
    )
    raw_full_payment_added = len(candidates) > full_payment_before
    if not raw_full_payment_added and adjusted_amount_safe_to_pay is not None:
        _build_full_payment_and_wait(
            candidates,
            profile,
            request_date,
            desired_completion_date,
            requested_amount,
            adjusted_amount_safe_to_pay,
            adjusted_earliest_date_for_full_payment,
            requires_changes=True,
        )

    # (2) partial_payment: raw-safe only (spending changes never apply to
    # a partial-payment candidate in this engine).
    if (
        "partial_payment" in payment_methods_user_will_consider
        and allows_partial_payment
        and earliest_date_for_full_payment is not None
        and earliest_date_for_full_payment <= desired_completion_date
        and 0 < amount_safe_to_pay < requested_amount
    ):
        candidates.append(
            CandidatePlan(
                method="partial_payment",
                payment_option_id=None,
                legs=[
                    (request_date, amount_safe_to_pay),
                    (earliest_date_for_full_payment, requested_amount - amount_safe_to_pay),
                ],
                total_paid=requested_amount,
                completes_by_deadline=True,
                requires_spending_changes=False,
                start_date=request_date,
                num_payments=2,
            )
        )

    # (3) installments: supplied payment options only, never affected by
    # simulated spending changes.
    if "installments" in payment_methods_user_will_consider and max_installment_months is not None and not pd.isna(
        max_installment_months
    ):
        installment_rows = bundle.payment_options[
            bundle.payment_options["payment_method"] == "installments"
        ]
        for _, row in installment_rows.iterrows():
            number_of_payments = int(row["number_of_payments"])
            payment_frequency_days = float(row["payment_frequency_days"])
            months = number_of_payments * payment_frequency_days / 30.0
            if months > max_installment_months:
                continue
            first_payment_date = pd.Timestamp(row["first_payment_date"]).normalize()
            end_date = first_payment_date + (number_of_payments - 1) * pd.Timedelta(
                days=payment_frequency_days
            )
            legs = [
                (
                    first_payment_date + k * pd.Timedelta(days=payment_frequency_days),
                    float(row["payment_amount"]),
                )
                for k in range(number_of_payments)
            ]
            candidates.append(
                CandidatePlan(
                    method="installments",
                    payment_option_id=row["payment_option_id"],
                    legs=legs,
                    total_paid=float(row["total_payable_amount"]),
                    completes_by_deadline=(end_date <= desired_completion_date),
                    requires_spending_changes=False,
                    start_date=first_payment_date,
                    num_payments=number_of_payments,
                )
            )

    # (4) wait: raw earliest_date_for_full_payment only -- a spending
    # change affecting today's floor does not change when full payment
    # becomes safe on its own timeline.
    if (
        earliest_date_for_full_payment is not None
        and earliest_date_for_full_payment > request_date
        and "full_payment" in payment_methods_user_will_consider
    ):
        candidates.append(
            CandidatePlan(
                method="wait",
                payment_option_id=None,
                legs=[(earliest_date_for_full_payment, requested_amount)],
                total_paid=requested_amount,
                completes_by_deadline=(earliest_date_for_full_payment <= desired_completion_date),
                requires_spending_changes=False,
                start_date=earliest_date_for_full_payment,
                num_payments=1,
            )
        )

    # (5) not_recommended: unconditional fallback.
    candidates.append(
        CandidatePlan(
            method="not_recommended",
            payment_option_id=None,
            legs=[],
            total_paid=0.0,
            completes_by_deadline=False,
            requires_spending_changes=False,
            start_date=request_date,
            num_payments=0,
        )
    )

    return candidates
