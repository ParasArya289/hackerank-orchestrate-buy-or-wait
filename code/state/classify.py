"""Cash-state classification for financial events.

Per AGENTS.md section 6.3 (Financial Decision Rules) and problem_statement.md
"90-Day Safety Check": every financial event must be classified into exactly
one cash-state treatment before it can be used in a forecast.

Rules applied here (do not re-derive elsewhere -- this is the single source
of truth for cash-state treatment):
- cancelled / failed / unrealized -> excluded entirely, never counted
- settled -> historical fact, counted
- pending debit -> reserved as a future cash outflow, counted
- pending credit -> NOT counted until it settles (bonuses, commissions,
  refunds, lottery proceeds, investment gains all fall in this bucket)
- scheduled -> counted as a known future event
- non_cash direction -> never counted, regardless of status (investment
  valuations/unrealized gains never count as cash)
"""

from __future__ import annotations

import pandas as pd

CASH_COUNTED_STATUSES = {"settled", "pending", "scheduled"}
EXCLUDED_STATUSES = {"cancelled", "failed", "unrealized"}


def classify_event(event_row: pd.Series) -> dict:
    """Classify a single event row into a cash-state treatment.

    Returns a dict with keys:
        cash_state: str -- the event's status-derived state label
        counts_toward_forecast: bool -- whether it should be counted as cash
        treatment: str -- the specific rule applied (for traceability)
    """
    status = event_row.get("status")
    direction = event_row.get("direction")

    # non_cash always excluded, regardless of status (checked first so it
    # takes precedence over an otherwise-countable status like "settled").
    if direction == "non_cash":
        return {
            "cash_state": status,
            "counts_toward_forecast": False,
            "treatment": "non_cash",
        }

    if status in ("cancelled", "failed", "unrealized"):
        return {
            "cash_state": status,
            "counts_toward_forecast": False,
            "treatment": "excluded",
        }

    if status == "settled":
        return {
            "cash_state": status,
            "counts_toward_forecast": True,
            "treatment": "historical",
        }

    if status == "pending" and direction == "debit":
        return {
            "cash_state": status,
            "counts_toward_forecast": True,
            "treatment": "reserve_pending_debit",
        }

    if status == "pending" and direction == "credit":
        return {
            "cash_state": status,
            "counts_toward_forecast": False,
            "treatment": "exclude_pending_credit",
        }

    if status == "scheduled":
        return {
            "cash_state": status,
            "counts_toward_forecast": True,
            "treatment": "future_scheduled",
        }

    # Unknown status/direction combination: conservative default -- exclude
    # rather than silently count an unrecognized state.
    return {
        "cash_state": status,
        "counts_toward_forecast": False,
        "treatment": "excluded_unrecognized",
    }


def classify_events(events_df: pd.DataFrame) -> pd.DataFrame:
    """Apply classify_event row-wise, returning a new DataFrame.

    Adds three columns: cash_state, counts_toward_forecast, treatment.
    Does not mutate the input DataFrame.
    """
    result = events_df.copy()
    classifications = result.apply(classify_event, axis=1, result_type="expand")
    result["cash_state"] = classifications["cash_state"]
    result["counts_toward_forecast"] = classifications["counts_toward_forecast"]
    result["treatment"] = classifications["treatment"]
    return result
