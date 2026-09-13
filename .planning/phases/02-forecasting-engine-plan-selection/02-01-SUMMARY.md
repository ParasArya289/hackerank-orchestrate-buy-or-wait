---
phase: 02-forecasting-engine-plan-selection
plan: 01
subsystem: forecasting
tags: [pandas, cash-flow-forecasting, recurrence-projection, balance-safety-check]

# Dependency graph
requires:
  - phase: 01-data-layer-financial-state-reconstruction (plan 02)
    provides: code/state package (build_financial_state, FinancialState, RecurrenceInfo, counts_toward_forecast classification)
provides:
  - code/forecast package with project_balance(financial_state, starting_balance, request_date, horizon_days=90) -> list[DailyBalance]
  - compute_amount_safe_to_pay(daily_balances, requested_amount, minimum_balance_to_keep) -> float
  - compute_earliest_date_for_full_payment(daily_balances, requested_amount, minimum_balance_to_keep) -> pd.Timestamp | None
affects: [02-02-plan-selection, 02-03]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "project_balance never re-derives cash-state rules; it filters strictly on Phase 1's counts_toward_forecast==True column and reuses the _settlement_or_event_date precedence from code/dataio/join.py"
    - "Recurring categories (RecurrenceInfo.is_recurring==True) are excluded from the one-time event pass and instead projected forward from their last settled occurrence at interval_days cadence, using typical_amount signed by that category's most recent settled row's direction"
    - "amount_safe_to_pay is computed analytically (min projected balance across the whole horizon minus minimum_balance_to_keep, clipped to [0, requested_amount], floored to 2 decimals) rather than by brute-force search"
    - "DailyBalance.events_applied records which real event_ids (or synthetic projected:{category}:{n} labels) contributed to each day's balance change, for traceability (threat model T-02-02)"

key-files:
  created:
    - code/forecast/__init__.py
    - code/forecast/balance.py
    - code/forecast/safety.py
    - code/tests/test_forecast.py
  modified: []

key-decisions:
  - "Test fixtures are fully synthetic (constructed FinancialState/DailyBalance instances) rather than dataset-backed, per the Phase 2 planning decision recorded in STATE.md, so expected numbers are pinned exactly rather than drifting with dataset re-derivation"
  - "Recurring-category sign is read from the direction column of the most recent settled row in that category (not inferred from an amount delta), matching recurrence.py's recent-window amount-stability design so step changes (raises, rent increases) still forecast at the correct sign and new level"
  - "A recurring category's concrete one-time rows are excluded from the one-time pass entirely (not just guarded per-date) since detect_recurring's own is_recurring flag already means that category's historical instances were used to derive typical_amount/interval_days; an explicit per-date guard is still applied so a future concrete row (e.g. a scheduled row) at the exact same calendar date as a projected occurrence never double-counts"

requirements-completed: [FORECAST-01, FORECAST-02, FORECAST-03]

# Metrics
duration: 12min
completed: 2026-09-13
---

# Phase 2 Plan 1: Forecasting Engine Summary

**`code/forecast` package: a 90-day daily balance projection combining current balance, one-time known events, and Phase 1's detected recurring patterns, plus analytically-derived `amount_safe_to_pay`/`earliest_date_for_full_payment` safety computations that never re-derive Phase 1's cash-state classification.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-09-13T07:07:00Z
- **Completed:** 2026-09-13T07:19:31Z
- **Tasks:** 2
- **Files modified:** 4 (all new)

## Accomplishments
- `project_balance(financial_state, starting_balance, request_date, horizon_days=90)` returns exactly `horizon_days + 1` `DailyBalance` entries with strictly non-decreasing, 1-day-incrementing dates, driven only by rows where `counts_toward_forecast == True`.
- Recurring categories (rent, salary, etc.) are projected forward from their last settled occurrence at `interval_days` cadence using `typical_amount`, signed by the most recent settled row's `direction` — verified with a synthetic rent fixture that correctly drops the balance on each of 3 in-window monthly occurrences and never invents a transaction on any other day.
- One-time events (scheduled/pending-debit/settled) apply on their exact `settlement_date`-or-`event_date` cash-movement date, reusing `code/dataio/join.py`'s `_settlement_or_event_date` precedence exactly.
- Rows with `counts_toward_forecast == False` (e.g. pending credits, cancelled/unrealized) are proven to never affect the projection: a constructed test asserts the projected balance sequence is byte-identical whether or not such a row is present in the input events DataFrame.
- `compute_amount_safe_to_pay` computes the max safe one-time payment analytically as `min(daily_balances) - minimum_balance_to_keep`, clipped to `[0, requested_amount]` and floored to 2 decimals — the `0 <= amount_safe_to_pay <= requested_amount` invariant (AGENTS.md OUT-02) is enforced at the source before Plan 02/03 ever see the value.
- `compute_earliest_date_for_full_payment` scans chronologically for the first day where paying the full `requested_amount` keeps every subsequent day `>= minimum_balance_to_keep`, returning `None` if no such day exists in the 90-day window.
- Verified against the full real dataset: ran `project_balance` + both safety functions across all 250 `requests.csv` rows with zero exceptions, and confirmed the `0 <= safe <= requested_amount` invariant holds in every case.

## Task Commits

Each task was committed atomically (TDD: RED then GREEN):

1. **RED (both tasks): failing tests for balance projection and safety computation** - `c5fece7` (test)
2. **Task 1: 90-day daily balance projection** - `731b981` (feat)
3. **Task 2: amount_safe_to_pay and earliest_date_for_full_payment** - `2127045` (feat)

**Plan metadata:** (this commit)

_Note: both tasks share a single RED commit since the test file was written up front covering both behaviors together; each task's GREEN implementation was then committed separately._

## Files Created/Modified
- `code/forecast/balance.py` - `DailyBalance` dataclass, `project_balance()` combining one-time and recurring-projected cash events
- `code/forecast/safety.py` - `compute_amount_safe_to_pay()`, `compute_earliest_date_for_full_payment()`
- `code/forecast/__init__.py` - package exports (`DailyBalance`, `project_balance`, `compute_amount_safe_to_pay`, `compute_earliest_date_for_full_payment`)
- `code/tests/test_forecast.py` - 10 unittest cases (4 for `project_balance`, 6 for the safety functions)

## Decisions Made
- See `key-decisions` in frontmatter: synthetic fixtures over dataset-backed fixtures, direction-based (not delta-based) sign inference for recurring categories, and full exclusion of a recurring category's concrete rows from the one-time pass with an added per-date duplicate guard.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed own test fixture bugs discovered during RED->GREEN**
- **Found during:** Task 1 (initial `project_balance` implementation, first test run)
- **Issue:** Two bugs in the test file itself (not the implementation): (a) `_events_df([])` crashed with `KeyError: 'event_date'` when building an empty-rows DataFrame, since no columns existed to convert; (b) the recurring-rent test asserted "at most 3 distinct balances" but the correct 90-day window from the test's `request_date` actually spans 3 in-window monthly rent occurrences (Jan 31, Mar 1, Mar 31), producing 4 correct distinct balance levels, not the incorrectly-eyeballed 3.
- **Fix:** (a) `_events_df` now returns an empty DataFrame with the expected columns when `rows` is empty, before attempting date conversion. (b) Rewrote the assertion to check that the distinct balances form an exact arithmetic sequence `10000 - i * 5148` for as many occurrences as actually land in-window, rather than a hardcoded count.
- **Files modified:** code/tests/test_forecast.py
- **Verification:** All 10 forecast tests pass; manually traced the 3 projected occurrence dates via a scratch script to confirm the corrected expectation is right, not just made to pass.
- **Committed in:** `731b981` (Task 1 commit, alongside the balance.py implementation)

---

**Total deviations:** 1 auto-fixed (test-fixture bug, Rule 1)
**Impact on plan:** No implementation logic deviated from the plan's specified algorithm. The fix was entirely in test scaffolding written during this same execution, corrected before commit. No scope creep.

## Issues Encountered

None beyond the self-authored test fixture bugs documented above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `code/forecast.project_balance` and `code/forecast.compute_amount_safe_to_pay`/`compute_earliest_date_for_full_payment` are ready for Plan 02 (plan-selection) to call directly, per the interface contract this plan's frontmatter documented.
- Verified against every request_id in the full 250-row `requests.csv` with zero exceptions; the `0 <= amount_safe_to_pay <= requested_amount` invariant holds in every case.
- Plan 02 (plan-selection) still owns: `desired_completion_date` enforcement, payment-option eligibility, `spending_changes_needed` logic, and `apply_spending_changes_to_state`/`recompute_safety_with_changes` — none of that was implemented here, matching this plan's explicit scope boundary.
- No blockers identified for Plan 02/03.

---
*Phase: 02-forecasting-engine-plan-selection*
*Completed: 2026-09-13*

## Self-Check: PASSED

All key files confirmed present on disk (code/forecast/__init__.py, balance.py, safety.py, code/tests/test_forecast.py). All three commits (c5fece7, 731b981, 2127045) confirmed present in git log. Full test suite (41 tests: 10 forecast + 19 state + 12 dataio) passes with 0 failures, 0 errors. Both plan-level verification commands re-run and pass. Full-dataset smoke test across all 250 requests.csv rows completes with zero exceptions, and the OUT-02 invariant (0 <= amount_safe_to_pay <= requested_amount) holds for every row.
