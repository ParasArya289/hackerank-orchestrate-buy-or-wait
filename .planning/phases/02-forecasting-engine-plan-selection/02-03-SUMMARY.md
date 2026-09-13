---
phase: 02-forecasting-engine-plan-selection
plan: 03
subsystem: output-pipeline
tags: [pandas, csv, deterministic-pipeline, output-contract]

# Dependency graph
requires:
  - phase: 02-forecasting-engine-plan-selection (plan 01)
    provides: project_balance, compute_amount_safe_to_pay, compute_earliest_date_for_full_payment
  - phase: 02-forecasting-engine-plan-selection (plan 02)
    provides: determine_eligible_plans, select_best_plan, build_payment_plan_string, select_spending_changes, recompute_safety_with_changes
provides:
  - "Single-request pipeline: build_output_row(request_id, tables=None) -> fully populated 8-key output row dict"
  - "derive_affordability_status(selected_plan, amount_safe_to_pay, requested_amount) -> one of 4 allowed enum values"
  - "run_all_requests(dataset_dir='dataset') -> list[dict] over the full requests.csv"
  - "write_output_csv(rows, path='dataset/output.csv') -> writes the exact 8-column contract, overwriting the blank template"
  - "dataset/output.csv populated for all 250 requests"
affects: [phase-03-llm-integration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "PHASE 3 EXTENSION POINT comment marks the decision_explanation placeholder string for later LLM-generated prose swap-in without touching any other column"
    - "Raw (pre-spending-change) amount_safe_to_pay/earliest_date_for_full_payment are always reported in the output row unconditionally; changes-adjusted values only ever feed determine_eligible_plans, never the reported amount_safe_to_pay/earliest_date_for_full_payment fields"
    - "not_affordable (selected plan == not_recommended) always forces earliest_date_for_full_payment to empty string, even when a raw earliest_date_for_full_payment value exists in isolation"

key-files:
  created:
    - code/output/__init__.py
    - code/output/assemble.py
    - code/output/writer.py
    - code/tests/test_output.py
  modified:
    - dataset/output.csv

key-decisions:
  - "derive_affordability_status maps a full_payment CandidatePlan with requires_spending_changes=True to affordable_with_plan (not affordable_now), per problem_statement.md's affordable_with_plan definition and the plan's synthetic fixture"
  - "spending_changes_needed reports whatever select_spending_changes selected regardless of which plan ultimately won, since it is informative evidence even when the winning plan did not strictly require it"
  - "amount_safe_to_pay in the output row is always the raw (pre-spending-change) value, defensively re-clipped to [0, requested_amount] at assembly time (threat model T-02-08, belt-and-suspenders against any future forecast-layer regression)"
  - "dataset/sample_requests.csv request_06's own specific numbers remain a documented, accepted divergence (per 02-03-PLAN.md's Known Divergence note) -- not re-litigated in this plan; the general changes-adjusted full_payment mechanism it illustrates is verified via a synthetic streaming-category fixture instead"

requirements-completed: [OUT-01, OUT-02, OUT-04]

# Metrics
duration: 55min
completed: 2026-09-13
---

# Phase 2 Plan 3: Output Row Assembly and Full-Dataset Writer Summary

**Single-request pipeline (`code/output/assemble.py`) wires Plan 01's forecast engine and Plan 02's plan-selection logic into one 8-column output row dict, and a full-dataset runner/writer (`code/output/writer.py`) produces the first real, invariant-checked `dataset/output.csv` for all 250 requests.**

## Performance

- **Duration:** ~55 min
- **Started:** 2026-09-13T06:40:00Z (approx, per session start)
- **Completed:** 2026-09-13T07:35:42Z
- **Tasks:** 2/2 completed
- **Files modified:** 5 (4 created, 1 regenerated)

## Accomplishments
- `build_output_row(request_id, tables=None)` assembles a fully-populated, invariant-enforced 8-key output row for any request_id, wiring FinancialState reconstruction, raw + changes-adjusted forecasting, and plan selection end-to-end
- `derive_affordability_status` correctly derives all 4 allowed `affordability_status` enum values from the selected `CandidatePlan`, including the `full_payment` + `requires_spending_changes=True` -> `affordable_with_plan` branch (the mechanism `dataset/sample_requests.csv` request_06 illustrates)
- `run_all_requests` + `write_output_csv` produced `dataset/output.csv` with exactly 250 rows, correct column order, and zero invariant violations across the full dataset
- Caught and fixed a genuine bug (not in the original plan text but required by the plan's own must_haves truth) where `not_affordable` rows could leak a non-empty `earliest_date_for_full_payment`

## Task Commits

Each task was committed atomically:

1. **Task 1: Single-request output row assembly with affordability_status derivation** - `9e498d7` (feat)
2. **Fix: force empty earliest_date_for_full_payment for not_affordable rows** - `f141cf0` (fix, Rule 1 auto-fix discovered during Task 2 verification)
3. **Task 2: Full-dataset run, output.csv writer, and invariant verification** - `85a0168` (feat)

_Note: the Rule 1 bugfix commit sits between Task 1 and Task 2 chronologically because it was discovered while running Task 2's full-dataset invariant verification, but the code it touches (`code/output/assemble.py`) is Task 1's file._

## Files Created/Modified
- `code/output/__init__.py` - exports `build_output_row`, `derive_affordability_status`
- `code/output/assemble.py` - `build_output_row` (per-request pipeline) and `derive_affordability_status` (plan -> enum mapping)
- `code/output/writer.py` - `run_all_requests` (full-dataset run, zero-tolerance for silent per-request failures), `write_output_csv` (hardcoded-fieldnames CSV writer), `__main__` block with post-write invariant verification
- `code/tests/test_output.py` - 8 test methods covering all `derive_affordability_status` branches, a live `request_113` smoke test, a synthetic streaming-fixture end-to-end pipeline test, and a regression test for the `not_affordable`-forces-empty-date fix
- `dataset/output.csv` - regenerated with 250 real rows (was the blank template)

## Decisions Made
- Kept `decision_explanation` as a deterministic, grounded placeholder string (method + safe amount + currency + optional spending-change/requires-changes context), marked with a `# PHASE 3 EXTENSION POINT` comment so Phase 3 can swap in LLM-generated prose without touching any other column
- `spending_changes_needed` surfaces the spending changes `select_spending_changes` selected regardless of which plan ultimately won (e.g. a `partial_payment` plan can still surface an available spending change), matching problem_statement.md's "flexible expenses that must be stopped or reduced" framing
- Followed the plan's exact 13-step `build_output_row` action spec verbatim, including the raw-vs-adjusted value separation for `amount_safe_to_pay`/`earliest_date_for_full_payment`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] not_affordable rows leaked a non-empty earliest_date_for_full_payment**
- **Found during:** Task 2's full-dataset invariant verification (running the acceptance-criteria spot-check for `affordable_now => earliest_date_for_full_payment == request_date`, which prompted checking the symmetric `not_affordable` case too)
- **Issue:** `build_output_row`'s step-10 logic only special-cased `affordability_status == "affordable_now"`; for `not_affordable` rows (selected plan == `not_recommended`) it fell through to reporting the raw `earliest_date_for_full_payment` whenever that raw value happened to be non-null in isolation -- e.g. a user profile that does not accept `full_payment` as a payment method at all still has a raw `earliest_date_for_full_payment` computed by Plan 01's pure forecast function, even though no plan using it is ever eligible. This violated the plan's own must_haves truth: "not_affordable/never-safe implies earliest_date_for_full_payment is empty". 8 of 250 full-dataset rows were affected (e.g. `request_79`, `request_133`, `request_139`, `request_141`, `request_142`).
- **Fix:** Added an explicit `affordability_status == "not_affordable"` branch in `build_output_row` that forces `earliest_date_str = ""` before falling through to the raw-value branch.
- **Files modified:** `code/output/assemble.py`, `code/tests/test_output.py` (added a regression test using a variant of the synthetic fixture with an empty `payment_methods_user_will_consider`)
- **Verification:** Full test suite (73/73) passes; full-dataset re-run confirms `not_affordable` violations dropped from 8 to 0 while `affordable_now` mismatches remain 0.
- **Committed in:** `f141cf0`

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug fix)
**Impact on plan:** Necessary for correctness against the plan's own must_haves truth; no scope creep, no architectural change.

## Issues Encountered
None beyond the deviation documented above.

## User Setup Required
None - no external service configuration required. This plan does not call Ollama/any LLM; Phase 3 owns that integration.

## Next Phase Readiness

Phase 2 (Forecasting Engine & Plan Selection) is now fully complete: all 3 plans (01-forecast, 02-plan-selection, 03-output-assembly) executed and tested. `dataset/output.csv` has real, invariant-checked predictions for all 250 requests with a deterministic `decision_explanation` placeholder. Phase 3 (LLM Integration) can now:
- Replace the `# PHASE 3 EXTENSION POINT` placeholder in `code/output/assemble.py` with real LLM-generated prose grounded in the same computed facts (method, amount_safe_to_pay, currency, spending changes), without touching any other column
- Reuse `build_output_row`/`run_all_requests`/`write_output_csv` unchanged as the assembly/writing layer
- No blockers identified.

---
*Phase: 02-forecasting-engine-plan-selection*
*Completed: 2026-09-13*

## Self-Check: PASSED

All created files and commit hashes verified present.
