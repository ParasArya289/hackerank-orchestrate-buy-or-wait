"""Currency conversion using dated exchange_rates.csv rows.

Per AGENTS.md: never invent an unsupported exchange rate. If a
(date, from_currency, to_currency) pair (or its inverse) is not present in
exchange_rates.csv, convert_amount raises ValueError rather than guessing.
"""

from __future__ import annotations

import pandas as pd


def _normalize_date(on_date) -> str:
    """Normalize a date-like value to a 'YYYY-MM-DD' string."""
    return pd.Timestamp(on_date).strftime("%Y-%m-%d")


def build_rate_index(exchange_rates_df: pd.DataFrame) -> dict[tuple[str, str, str], float]:
    """Build a (rate_date_str, from_currency, to_currency) -> rate index."""
    index: dict[tuple[str, str, str], float] = {}
    for row in exchange_rates_df.itertuples(index=False):
        rate_date = _normalize_date(row.rate_date)
        index[(rate_date, row.from_currency, row.to_currency)] = float(row.rate)
    return index


def convert_amount(
    amount: float,
    from_currency: str,
    to_currency: str,
    on_date,
    rate_index: dict[tuple[str, str, str], float],
) -> float:
    """Convert amount from from_currency to to_currency using the rate on on_date.

    Looks up the exact (date, from_currency, to_currency) key first; if
    missing, tries the inverse (date, to_currency, from_currency) key and
    divides. Raises ValueError if neither is present.
    """
    if from_currency == to_currency:
        return float(amount)

    date_str = _normalize_date(on_date)

    direct_key = (date_str, from_currency, to_currency)
    if direct_key in rate_index:
        return float(amount) * rate_index[direct_key]

    inverse_key = (date_str, to_currency, from_currency)
    if inverse_key in rate_index:
        return float(amount) / rate_index[inverse_key]

    raise ValueError(
        f"No exchange rate found for {from_currency}->{to_currency} "
        f"(or inverse) on {date_str}"
    )
