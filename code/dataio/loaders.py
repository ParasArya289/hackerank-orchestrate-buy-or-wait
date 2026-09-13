"""CSV loaders for the Buy or Wait? dataset tables.

Every loader returns a pandas DataFrame with explicit dtypes:
- date-like columns are parsed to pd.Timestamp via pd.to_datetime
- numeric columns are parsed as float with errors="coerce" so blank cells
  become NaN (never silently 0)
- pipe-delimited multi-value profile fields are split into Python lists

See AGENTS.md section 6.1 (Dataset Contract) and 6.3 (Financial Decision
Rules) for the source-of-truth semantics these loaders must preserve.
"""

from __future__ import annotations

import os

import pandas as pd

DATASET_DIR_DEFAULT = "dataset"


def _split_pipe(series: pd.Series) -> pd.Series:
    """Split a pipe-delimited string column into Python lists.

    Blank/NaN cells become [] (never [""])."""

    def _split_one(value):
        if pd.isna(value):
            return []
        text = str(value).strip()
        if text == "":
            return []
        return [part for part in text.split("|") if part != ""]

    return series.apply(_split_one)


def _to_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _to_datetime(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce")


def load_financial_events(path: str = "dataset/financial_events.csv") -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    df["amount"] = _to_float(df["amount"])
    df["minimum_allowed_amount"] = _to_float(df["minimum_allowed_amount"])
    df["event_date"] = _to_datetime(df["event_date"])
    df["settlement_date"] = _to_datetime(df["settlement_date"])
    return df


def load_financial_profiles(path: str = "dataset/financial_profiles.csv") -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    df["current_available_balance"] = _to_float(df["current_available_balance"])
    df["minimum_balance_to_keep"] = _to_float(df["minimum_balance_to_keep"])
    df["max_installment_months"] = _to_float(df["max_installment_months"])
    for col in (
        "financial_priorities",
        "expense_categories_to_protect",
        "expense_categories_user_is_willing_to_reduce",
        "expense_categories_user_is_willing_to_stop",
        "payment_methods_user_will_consider",
    ):
        df[col] = _split_pipe(df[col])
    return df


def load_requests(path: str = "dataset/requests.csv") -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    df["requested_amount"] = _to_float(df["requested_amount"])
    df["request_date"] = _to_datetime(df["request_date"])
    df["desired_completion_date"] = _to_datetime(df["desired_completion_date"])
    return df


def load_payment_options(path: str = "dataset/request_payment_options.csv") -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    df["payment_amount"] = _to_float(df["payment_amount"])
    df["financing_fee"] = _to_float(df["financing_fee"])
    df["total_payable_amount"] = _to_float(df["total_payable_amount"])
    df["number_of_payments"] = _to_float(df["number_of_payments"])
    df["payment_frequency_days"] = _to_float(df["payment_frequency_days"])
    df["first_payment_date"] = _to_datetime(df["first_payment_date"])
    return df


def load_exchange_rates(path: str = "dataset/exchange_rates.csv") -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    df["rate"] = _to_float(df["rate"])
    df["rate_date"] = _to_datetime(df["rate_date"])
    return df


def load_messages(path: str = "dataset/messages.csv") -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    df["sent_at"] = _to_datetime(df["sent_at"])
    return df


def load_images(path: str = "dataset/images.csv") -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=True)
    return df


def load_all(dataset_dir: str = DATASET_DIR_DEFAULT) -> dict[str, pd.DataFrame]:
    """Load all 7 dataset tables, keyed by short table name."""
    return {
        "events": load_financial_events(os.path.join(dataset_dir, "financial_events.csv")),
        "profiles": load_financial_profiles(os.path.join(dataset_dir, "financial_profiles.csv")),
        "requests": load_requests(os.path.join(dataset_dir, "requests.csv")),
        "payment_options": load_payment_options(
            os.path.join(dataset_dir, "request_payment_options.csv")
        ),
        "exchange_rates": load_exchange_rates(os.path.join(dataset_dir, "exchange_rates.csv")),
        "messages": load_messages(os.path.join(dataset_dir, "messages.csv")),
        "images": load_images(os.path.join(dataset_dir, "images.csv")),
    }
