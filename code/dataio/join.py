"""Per-request join across all dataset tables.

build_request_bundle(request_id) is the single call site later phases use
to get everything needed for one request: the request row, the user's
profile, all of the user's financial events (blank amounts resolved,
converted to home currency), the request's payment options, and any
linked messages/images.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .fx import build_rate_index, convert_amount
from .loaders import load_all
from .vision_stub import resolve_all_blank_amounts


@dataclass
class RequestBundle:
    request: pd.Series
    profile: pd.Series
    events: pd.DataFrame
    payment_options: pd.DataFrame
    messages: pd.DataFrame
    images: pd.DataFrame


def _settlement_or_event_date(row: pd.Series):
    """Prefer settlement_date for rate lookups; fall back to event_date."""
    if pd.notna(row.get("settlement_date")):
        return row["settlement_date"]
    return row["event_date"]


def build_request_bundle(request_id: str, tables: dict[str, pd.DataFrame] | None = None) -> RequestBundle:
    if tables is None:
        tables = load_all()

    requests_df = tables["requests"]
    matches = requests_df[requests_df["request_id"] == request_id]
    if len(matches) == 0:
        raise KeyError(f"request_id {request_id!r} not found in requests table")
    request_row = matches.iloc[0]
    user_id = request_row["user_id"]

    profiles_df = tables["profiles"]
    profile_matches = profiles_df[profiles_df["user_id"] == user_id]
    if len(profile_matches) == 0:
        raise KeyError(f"user_id {user_id!r} not found in profiles table")
    profile_row = profile_matches.iloc[0]
    home_currency = profile_row["home_currency"]

    events_df = tables["events"]
    user_events = events_df[events_df["user_id"] == user_id].copy()
    user_events = resolve_all_blank_amounts(user_events, tables["images"])

    rate_index = build_rate_index(tables["exchange_rates"])

    def _convert_row(row: pd.Series):
        if row["direction"] == "non_cash":
            return float("nan")
        on_date = _settlement_or_event_date(row)
        return convert_amount(row["amount"], row["currency"], home_currency, on_date, rate_index)

    user_events["amount_home_currency"] = user_events.apply(_convert_row, axis=1)

    payment_options_df = tables["payment_options"]
    request_payment_options = payment_options_df[
        payment_options_df["request_id"] == request_id
    ].copy()

    messages_df = tables["messages"]
    request_messages = messages_df[
        (messages_df["user_id"] == user_id) | (messages_df["request_id"] == request_id)
    ].copy()

    images_df = tables["images"]
    request_images = images_df[
        (images_df["user_id"] == user_id) | (images_df["request_id"] == request_id)
    ].copy()

    return RequestBundle(
        request=request_row,
        profile=profile_row,
        events=user_events,
        payment_options=request_payment_options,
        messages=request_messages,
        images=request_images,
    )
