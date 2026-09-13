"""Full-dataset run and CSV writer (Phase 2 Plan 03, OUT-04).

run_all_requests(dataset_dir="dataset") loads every dataset table once
via code.dataio.loaders.load_all, then calls
code.output.assemble.build_output_row for every request_id in
requests.csv (in file order), collecting one output row dict per
request. Any per-request failure is re-raised with the offending
request_id attached -- never silently skipped (OUT-01 requires exactly
one row per request_id, zero tolerance for silent drops; threat model
T-02-07).

write_output_csv(rows, path="dataset/output.csv") writes those rows to
disk with a hardcoded fieldnames list (never derived from
rows[0].keys()) so column order is guaranteed even if a future change
reorders the dict, overwriting any existing content.
"""

from __future__ import annotations

import csv

from code.dataio.loaders import load_all
from code.output.assemble import build_output_row

FIELDNAMES = [
    "request_id",
    "amount_safe_to_pay",
    "affordability_status",
    "recommended_payment_method",
    "payment_plan",
    "earliest_date_for_full_payment",
    "spending_changes_needed",
    "decision_explanation",
]

ALLOWED_STATUSES = {"affordable_now", "affordable_with_plan", "affordable_later", "not_affordable"}
ALLOWED_METHODS = {"full_payment", "partial_payment", "installments", "wait", "not_recommended"}


def run_all_requests(dataset_dir: str = "dataset") -> list:
    """Load the full dataset once and build one output row per
    request_id in dataset/requests.csv, in file order. Re-raises any
    per-request failure with the offending request_id attached --
    never silently skips a row."""
    tables = load_all(dataset_dir)
    request_ids = tables["requests"]["request_id"].tolist()

    rows = []
    for request_id in request_ids:
        try:
            row = build_output_row(request_id, tables=tables)
        except Exception as e:
            raise RuntimeError(f"build_output_row failed for {request_id}: {e}") from e
        rows.append(row)
    return rows


def write_output_csv(rows: list, path: str = "dataset/output.csv") -> None:
    """Write `rows` to `path` as CSV with the exact 8 required columns,
    in the exact required order, overwriting any existing content."""
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _verify_invariants(dataset_dir: str = "dataset", path: str = "dataset/output.csv") -> None:
    """Post-write invariant check: reads dataset/output.csv (and
    dataset/requests.csv for cross-referencing requested_amount) back
    from disk and asserts every documented invariant holds across the
    full run."""
    requests_by_id = {}
    with open(f"{dataset_dir}/requests.csv", newline="") as f:
        for row in csv.DictReader(f):
            requests_by_id[row["request_id"]] = float(row["requested_amount"])

    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))

    if len(rows) != 250:
        raise AssertionError(f"Expected 250 data rows, found {len(rows)}")

    for row in rows:
        request_id = row["request_id"]

        try:
            amount_safe_to_pay = float(row["amount_safe_to_pay"])
        except (TypeError, ValueError) as e:
            raise AssertionError(
                f"{request_id}: amount_safe_to_pay does not parse as float ({row['amount_safe_to_pay']!r})"
            ) from e

        requested_amount = requests_by_id.get(request_id)
        if requested_amount is None:
            raise AssertionError(f"{request_id}: not found in dataset/requests.csv for cross-reference")

        if not (0 <= amount_safe_to_pay <= requested_amount + 1e-6):
            raise AssertionError(
                f"{request_id}: amount_safe_to_pay={amount_safe_to_pay} out of bounds "
                f"[0, {requested_amount}]"
            )

        if row["affordability_status"] not in ALLOWED_STATUSES:
            raise AssertionError(
                f"{request_id}: affordability_status={row['affordability_status']!r} not in {ALLOWED_STATUSES}"
            )

        if row["recommended_payment_method"] not in ALLOWED_METHODS:
            raise AssertionError(
                f"{request_id}: recommended_payment_method={row['recommended_payment_method']!r} "
                f"not in {ALLOWED_METHODS}"
            )

    print("All invariants passed")


if __name__ == "__main__":
    rows = run_all_requests()
    write_output_csv(rows)
    print(f"Wrote {len(rows)} rows to dataset/output.csv")
    _verify_invariants()
