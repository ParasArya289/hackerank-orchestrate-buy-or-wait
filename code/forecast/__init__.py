"""Deterministic 90-day balance forecasting engine.

project_balance(financial_state, starting_balance, request_date,
horizon_days=90) is the single call site Plan 02/03 need: it builds a
daily balance projection from Phase 1's FinancialState (classified
events + detected recurrence), combining one-time known events with
projected recurring occurrences.
"""

from .balance import DailyBalance, project_balance

__all__ = [
    "DailyBalance",
    "project_balance",
]
