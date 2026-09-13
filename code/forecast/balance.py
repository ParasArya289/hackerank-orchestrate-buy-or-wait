"""90-day daily balance projection.

project_balance(financial_state, starting_balance, request_date,
horizon_days=90) projects a user's daily cash balance forward from
request_date using:
  - one-time events (settled/pending-debit/scheduled) whose own cash
    movement date falls within the projection window, and
  - recurring categories detected by Phase 1's code.state.recurrence,
    projected forward at their typical_amount/interval_days cadence.

Only rows with counts_toward_forecast == True (Phase 1's classification,
see code/state/classify.py) are ever used -- this module never re-derives
cash-state rules, it trusts that column as the single source of truth
(threat model T-02-01).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from code.state.reconcile import FinancialState


@dataclass
class DailyBalance:
    date: pd.Timestamp
    balance: float
    events_applied: list[str] = field(default_factory=list)


def _settlement_or_event_date(row: pd.Series):
    """Prefer settlement_date for cash-movement timing; fall back to
    event_date. Mirrors code/dataio/join.py's _settlement_or_event_date
    exactly -- do not diverge from that precedence rule."""
    if pd.notna(row.get("settlement_date")):
        return row["settlement_date"]
    return row["event_date"]


def _signed_amount(row: pd.Series) -> float:
    """Debit subtracts, credit adds. Amounts are already in home currency
    (amount_home_currency), non-cash rows are filtered out before this is
    ever called."""
    amount = float(row["amount_home_currency"])
    if row["direction"] == "debit":
        return -amount
    if row["direction"] == "credit":
        return amount
    # Should never be reached: non_cash rows never have
    # counts_toward_forecast == True (classify.py), so they are filtered
    # out prior to this call. Conservative fallback: no impact.
    return 0.0


def project_balance(
    financial_state: FinancialState,
    starting_balance: float,
    request_date,
    horizon_days: int = 90,
) -> list[DailyBalance]:
    request_date = pd.Timestamp(request_date).normalize()
    horizon_end = request_date + pd.Timedelta(days=horizon_days)

    events = financial_state.events
    countable = events[events["counts_toward_forecast"] == True].copy()  # noqa: E712

    if len(countable):
        countable["_cash_date"] = countable.apply(_settlement_or_event_date, axis=1)
        countable["_cash_date"] = pd.to_datetime(countable["_cash_date"]).dt.normalize()
    else:
        countable["_cash_date"] = pd.Series(dtype="datetime64[ns]")

    recurring_categories = {
        category
        for category, info in financial_state.recurrence.items()
        if info.is_recurring
    }

    # Per-day net impact and the event_ids that contributed, keyed by
    # normalized Timestamp.
    daily_impact: dict[pd.Timestamp, float] = {}
    daily_events: dict[pd.Timestamp, list[str]] = {}

    def _add(date: pd.Timestamp, amount: float, event_id: str) -> None:
        if date < request_date or date > horizon_end:
            return
        daily_impact[date] = daily_impact.get(date, 0.0) + amount
        daily_events.setdefault(date, []).append(event_id)

    # One-time events: any row whose category is NOT recurring, applied
    # on its own cash-movement date. Rows before request_date are
    # historical and never projected forward individually (recurring
    # categories already summarize their history via typical_amount).
    one_time = countable[~countable["category"].isin(recurring_categories)]
    for _, row in one_time.iterrows():
        cash_date = row["_cash_date"]
        if pd.isna(cash_date) or cash_date < request_date:
            continue
        _add(cash_date, _signed_amount(row), str(row.get("event_id")))

    # Recurring categories: project forward from the last observed
    # settled occurrence date at interval_days cadence, using
    # typical_amount signed by that category's most recent settled row's
    # direction.
    for category in recurring_categories:
        info = financial_state.recurrence[category]
        if not info.interval_days:
            continue

        settled_rows = countable[
            (countable["category"] == category) & (countable["status"] == "settled")
        ].sort_values("_cash_date")
        if len(settled_rows) == 0:
            continue

        last_row = settled_rows.iloc[-1]
        last_date = last_row["_cash_date"]
        direction = last_row["direction"]
        signed_typical = info.typical_amount if direction == "credit" else -info.typical_amount

        # Dates that already have a concrete one-time row for this
        # category (any status) at that exact date -- skip generating a
        # duplicate recurring projection there.
        concrete_dates = set(
            countable[countable["category"] == category]["_cash_date"].dropna().tolist()
        )

        occurrence_date = last_date + pd.Timedelta(days=info.interval_days)
        occurrence_index = 1
        while occurrence_date <= horizon_end:
            if occurrence_date >= request_date and occurrence_date not in concrete_dates:
                _add(
                    occurrence_date,
                    signed_typical,
                    f"projected:{category}:{occurrence_index}",
                )
            occurrence_index += 1
            occurrence_date = last_date + pd.Timedelta(days=info.interval_days * (occurrence_index))

    # Build the running daily balance.
    results: list[DailyBalance] = []
    running = float(starting_balance)
    current = request_date
    while current <= horizon_end:
        impact = daily_impact.get(current, 0.0)
        running += impact
        events_applied = daily_events.get(current, [])
        results.append(DailyBalance(date=current, balance=running, events_applied=events_applied))
        current = current + pd.Timedelta(days=1)

    return results
