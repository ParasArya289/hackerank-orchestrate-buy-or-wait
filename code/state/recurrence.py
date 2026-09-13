"""Recurrence detection for a user's financial events.

Per AGENTS.md section 6.3: "Detect recurrence only when history supports
it." This module only flags a category as recurring when the observed
settled history actually shows a stable amount and a stable cadence --
never guessed from a single occurrence.

Confirmed canonical shape (session fact, do not re-derive): user_01,
category "rent", 6 rows, all 5148 ZAR, monthly cadence
(2023-10-02 .. 2024-03-02), status settled, flexibility fixed.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class RecurrenceInfo:
    is_recurring: bool
    category: str
    typical_amount: float
    interval_days: int | None
    occurrence_count: int


def detect_recurring(
    events_df: pd.DataFrame,
    user_id: str,
    category: str,
    amount_tolerance: float = 0.05,
    min_occurrences: int = 3,
    recent_window: int = 2,
) -> RecurrenceInfo:
    """Detect whether a user's events in `category` recur on a stable cadence.

    Filters to settled events for this user + category, sorts by
    event_date, and checks: enough occurrences, day-gaps between
    consecutive occurrences consistent within +/- 5 days of their median
    (covers ~28-31 day monthly variance), and amounts stable at the
    *current* level.

    The amount check only requires the most recent `recent_window`
    occurrences (default 2 -- the minimum that can confirm "the current
    level is stable") to be within `amount_tolerance` fractional variance
    of their own median -- not the full history. A one-time step change
    (a raise, a salary cut, a rent increase) that is itself stable going
    forward is still detected as recurring, at the new amount, rather
    than being masked by comparing against a stale full-history median
    or a window wide enough to straddle the transition. Cadence
    (`gaps_ok`) still requires `min_occurrences` (default 3) settled rows
    so a genuine periodic cadence is established. `typical_amount`
    reflects this recent, current-level median so forecasts project the
    amount the user actually receives/pays now.
    """
    subset = events_df[
        (events_df["user_id"] == user_id)
        & (events_df["category"] == category)
        & (events_df["status"] == "settled")
    ].copy()
    subset = subset.sort_values("event_date")

    occurrence_count = len(subset)

    if occurrence_count < min_occurrences:
        return RecurrenceInfo(
            is_recurring=False,
            category=category,
            typical_amount=float("nan"),
            interval_days=None,
            occurrence_count=occurrence_count,
        )

    amounts = subset["amount_home_currency"] if "amount_home_currency" in subset.columns else subset["amount"]
    amounts = amounts.astype(float)
    recent_amounts = amounts.tail(recent_window)
    median_amount = recent_amounts.median()

    if median_amount == 0 or pd.isna(median_amount):
        return RecurrenceInfo(
            is_recurring=False,
            category=category,
            typical_amount=float("nan"),
            interval_days=None,
            occurrence_count=occurrence_count,
        )

    amount_ok = (
        ((recent_amounts - median_amount).abs() / abs(median_amount)) <= amount_tolerance
    ).all()

    dates = pd.to_datetime(subset["event_date"])
    gaps = dates.diff().dropna().dt.days
    if len(gaps) == 0:
        return RecurrenceInfo(
            is_recurring=False,
            category=category,
            typical_amount=float("nan"),
            interval_days=None,
            occurrence_count=occurrence_count,
        )

    median_gap = gaps.median()
    gaps_ok = ((gaps - median_gap).abs() <= 5).all()

    if amount_ok and gaps_ok:
        return RecurrenceInfo(
            is_recurring=True,
            category=category,
            typical_amount=float(median_amount),
            interval_days=int(round(median_gap)),
            occurrence_count=occurrence_count,
        )

    return RecurrenceInfo(
        is_recurring=False,
        category=category,
        typical_amount=float("nan"),
        interval_days=None,
        occurrence_count=occurrence_count,
    )


def detect_all_recurring(events_df: pd.DataFrame, user_id: str) -> dict:
    """Run detect_recurring for every distinct category this user has events in."""
    user_events = events_df[events_df["user_id"] == user_id]
    categories = user_events["category"].dropna().unique()
    return {category: detect_recurring(events_df, user_id, category) for category in categories}
