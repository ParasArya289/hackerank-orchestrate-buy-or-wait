"""Single-request output-row assembly (Phase 2 Plan 03).

build_output_row(request_id, tables=None) wires together the whole
Phase 2 pipeline for one request_id:
    code.dataio.join.build_request_bundle   -> RequestBundle
    code.state.reconcile.build_financial_state -> FinancialState
    code.forecast.balance.project_balance   -> raw daily balances
    code.forecast.safety.compute_amount_safe_to_pay /
        compute_earliest_date_for_full_payment -> raw safety numbers
    code.plan.spending_changes.select_spending_changes /
        recompute_safety_with_changes -> changes-adjusted safety numbers
    code.plan.eligibility.determine_eligible_plans -> candidate plans
        (raw and changes-adjusted)
    code.plan.select.select_best_plan / build_payment_plan_string
        -> the winning CandidatePlan and its payment_plan string

into one dict with the 8 required output columns, in the required
order.

derive_affordability_status(selected_plan, amount_safe_to_pay,
requested_amount) maps the selected CandidatePlan's method/
completes_by_deadline/requires_spending_changes flags to one of the 4
allowed affordability_status enum values per problem_statement.md's
"Allowed values" (verbatim semantics restated in this plan's Dataset
Facts / Known Divergence note).
"""

from __future__ import annotations

import pandas as pd

from code.dataio.join import build_request_bundle
from code.forecast.balance import project_balance
from code.forecast.safety import (
    compute_amount_safe_to_pay,
    compute_earliest_date_for_full_payment,
)
from code.plan.eligibility import determine_eligible_plans
from code.plan.select import build_payment_plan_string, select_best_plan
from code.plan.spending_changes import (
    recompute_safety_with_changes,
    select_spending_changes,
)
from code.state.reconcile import build_financial_state

_EPSILON = 1e-6


def derive_affordability_status(selected_plan, amount_safe_to_pay: float, requested_amount: float) -> str:
    """Map the selected CandidatePlan to one of the 4 allowed
    affordability_status values.

    - not_recommended -> not_affordable (cannot complete safely within
      the forecast period).
    - wait -> affordable_later (full amount expected to become safe
      later).
    - full_payment that is safe today, completes by deadline, and did
      NOT require a simulated spending change -> affordable_now.
    - Everything else that completes the full requested_amount --
      partial_payment, installments, or a full_payment that only
      qualified via requires_spending_changes=True -- -> affordable_with_plan.
      This is the branch problem_statement.md's affordable_with_plan
      definition ("full request completed through a partial-payment
      schedule, installments, or permitted spending changes") requires,
      and the branch dataset/sample_requests.csv request_06 illustrates
      (see this plan's Known Divergence note for why request_06's exact
      numbers are not asserted as a test oracle here).
    """
    if selected_plan.method == "not_recommended":
        return "not_affordable"
    if selected_plan.method == "wait":
        return "affordable_later"
    if (
        selected_plan.method == "full_payment"
        and amount_safe_to_pay >= requested_amount - _EPSILON
        and selected_plan.completes_by_deadline
        and not selected_plan.requires_spending_changes
    ):
        return "affordable_now"
    return "affordable_with_plan"


def build_output_row(request_id: str, tables: "dict | None" = None) -> dict:
    """Assemble one fully-populated output row for `request_id`.

    Returns a dict with exactly these 8 keys, in this exact order
    (Python 3.7+ dicts preserve insertion order -- this determines CSV
    column order downstream in code.output.writer):
        request_id, amount_safe_to_pay, affordability_status,
        recommended_payment_method, payment_plan,
        earliest_date_for_full_payment, spending_changes_needed,
        decision_explanation
    """
    bundle = build_request_bundle(request_id, tables=tables)
    financial_state = build_financial_state(request_id, tables=tables)

    request_date = pd.Timestamp(bundle.request["request_date"]).normalize()
    requested_amount = float(bundle.request["requested_amount"])
    minimum_balance_to_keep = float(bundle.profile["minimum_balance_to_keep"])
    starting_balance = float(bundle.profile["current_available_balance"])

    # (2)-(3): raw (pre-spending-change) safety numbers. amount_safe_to_pay
    # here is what gets reported in the output row's amount_safe_to_pay
    # field, unconditionally, regardless of which plan is ultimately
    # selected (problem_statement.md: "the most the user can pay today
    # before optional spending changes" -- never overwritten by the
    # adjusted computation).
    daily_balances = project_balance(financial_state, starting_balance, request_date, horizon_days=90)
    amount_safe_to_pay = compute_amount_safe_to_pay(
        daily_balances, requested_amount, minimum_balance_to_keep
    )
    earliest_date_for_full_payment = compute_earliest_date_for_full_payment(
        daily_balances, requested_amount, minimum_balance_to_keep
    )

    # (4)-(5): changes-adjusted safety numbers, only attempted when at
    # least one spending-change candidate exists.
    spending_changes = select_spending_changes(financial_state, bundle.profile)
    if spending_changes:
        adjusted_amount_safe_to_pay, adjusted_earliest_date_for_full_payment = (
            recompute_safety_with_changes(
                financial_state,
                spending_changes,
                starting_balance,
                request_date,
                requested_amount,
                minimum_balance_to_keep,
                horizon_days=90,
            )
        )
    else:
        adjusted_amount_safe_to_pay = None
        adjusted_earliest_date_for_full_payment = None

    # (6)-(8): eligible candidates, best-ranked selection, payment_plan
    # string.
    eligible_plans = determine_eligible_plans(
        bundle,
        amount_safe_to_pay,
        earliest_date_for_full_payment,
        adjusted_amount_safe_to_pay,
        adjusted_earliest_date_for_full_payment,
    )
    selected_plan = select_best_plan(eligible_plans)
    payment_plan = build_payment_plan_string(selected_plan)

    # (9): affordability_status derived from the selected plan and the
    # RAW amount_safe_to_pay (never the adjusted one).
    affordability_status = derive_affordability_status(
        selected_plan, amount_safe_to_pay, requested_amount
    )

    # (10): earliest_date_for_full_payment string -- uses the RAW
    # earliest_date_for_full_payment, never the adjusted one, per
    # problem_statement.md's definition of this field as computed
    # "without optional spending changes".
    if affordability_status == "affordable_now":
        earliest_date_str = request_date.strftime("%Y-%m-%d")
    elif affordability_status == "not_affordable":
        # not_affordable means the selected plan is not_recommended --
        # no full payment is ever safe under this user's accepted
        # payment methods/deadline, so this field must be empty even if
        # a raw earliest_date_for_full_payment value exists in isolation
        # (e.g. the user does not accept full_payment at all).
        earliest_date_str = ""
    elif earliest_date_for_full_payment is not None:
        earliest_date_str = pd.Timestamp(earliest_date_for_full_payment).strftime("%Y-%m-%d")
    else:
        earliest_date_str = ""

    # (11): spending_changes_needed reports the changes that were
    # selected/simulated regardless of which plan won -- informative even
    # when the winning plan did not strictly need them.
    spending_changes_str = "|".join(spending_changes) if spending_changes else "none"

    # (12): amount_safe_to_pay rounded to 2 decimals, defensively
    # re-clipped to [0, requested_amount] (belt-and-suspenders against any
    # future regression in the forecast layer -- threat model T-02-08).
    amount_safe_to_pay_rounded = round(float(amount_safe_to_pay), 2)
    amount_safe_to_pay_rounded = max(0.0, min(amount_safe_to_pay_rounded, requested_amount))

    # (13): deterministic, grounded decision_explanation placeholder.
    # PHASE 3 EXTENSION POINT: replace with gemma4-generated prose grounded in these same facts
    home_currency = bundle.profile["home_currency"]
    method_label = selected_plan.method.replace("_", " ").title()
    decision_explanation = (
        f"{method_label} recommended: safe amount is {amount_safe_to_pay_rounded} {home_currency}."
    )
    if selected_plan.requires_spending_changes and spending_changes:
        decision_explanation += f" Requires stopping/reducing: {spending_changes_str}."
    elif spending_changes and spending_changes_str != "none" and selected_plan.method != "not_recommended":
        decision_explanation += f" Available spending changes: {spending_changes_str}."

    return {
        "request_id": request_id,
        "amount_safe_to_pay": amount_safe_to_pay_rounded,
        "affordability_status": affordability_status,
        "recommended_payment_method": selected_plan.method,
        "payment_plan": payment_plan,
        "earliest_date_for_full_payment": earliest_date_str,
        "spending_changes_needed": spending_changes_str,
        "decision_explanation": decision_explanation,
    }
