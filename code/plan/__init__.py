"""code.plan -- candidate plan eligibility, spending-change selection, and
ranking/final-selection for the Buy or Wait? decision engine.

Public surface (see code/plan/eligibility.py, code/plan/spending_changes.py,
code/plan/select.py for docs):
    CandidatePlan, determine_eligible_plans
    select_spending_changes, apply_spending_changes_to_state,
    recompute_safety_with_changes
    rank_plans, select_best_plan, build_payment_plan_string
"""

from __future__ import annotations

from .eligibility import CandidatePlan, determine_eligible_plans
from .select import build_payment_plan_string, rank_plans, select_best_plan
from .spending_changes import (
    apply_spending_changes_to_state,
    recompute_safety_with_changes,
    select_spending_changes,
)

__all__ = [
    "CandidatePlan",
    "determine_eligible_plans",
    "select_spending_changes",
    "apply_spending_changes_to_state",
    "recompute_safety_with_changes",
    "rank_plans",
    "select_best_plan",
    "build_payment_plan_string",
]
