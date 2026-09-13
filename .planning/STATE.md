---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: in_progress
last_updated: "2026-09-13T07:37:30.368Z"
progress:
  total_phases: 4
  completed_phases: 2
  total_plans: 5
  completed_plans: 5
  percent: 50
---

# STATE.md

## Current Position

**Phase:** 2 — Forecasting Engine & Plan Selection — COMPLETE (3/3 plans)
**Next action:** Begin Phase 3 (LLM Integration, Local Ollama) — `/gsd:plan-phase 03` or `/gsd:execute-phase 03`

## Phase Status

| Phase | Status |
|---|---|
| 1. Data Layer & Financial State Reconstruction | Complete (2/2 plans) |
| 2. Forecasting Engine & Plan Selection | Complete (3/3 plans) |
| 3. LLM Integration (Local Ollama) | Not started |
| 4. Full-Dataset Run, Packaging & Submission Prep | Not started |

## Decisions

- Installed pandas via pip (no venv/requirements.txt existed); matches PROJECT.md's already-committed stack decision (01-01).
- Corrected `request_payment_options.csv` row count to the verified 790 data rows (plan stated 791) (01-01).
- All 16 blank-amount financial events resolved via manually-read linked PNGs into a hardcoded lookup table in `code/dataio/vision_stub.py`, with a marked Phase 3 extension point for the real qwen2.5vl Ollama call (01-01).
- `classify_event` checks `direction == "non_cash"` before status so investment valuations are always excluded from cash-flow counting regardless of status label (01-02).
- Image amendments are extracted for traceability but not re-applied on top of `build_request_bundle`'s events, since Plan 01's join step already resolves the same blank-amount fact via the linked image (01-02).
- `detect_recurring` amount-stability check now uses only the most recent 2 settled occurrences against their own median (cadence still requires 3), not full history against one global median — fixes a bug where any one-time step change (raise/cut) failed recurrence for ~40% of users, dropping future income from the forecast entirely (02-planning, commit `dc4224b`).
- `request_06` from `sample_requests.csv` is a known, accepted divergence: the deterministic engine now correctly forecasts user_06's salary and computes a different (higher, still-safe) `amount_safe_to_pay` than the sample's `603.3`, because the sample's ground truth also depends on interpreting `message_04`'s ambiguous "temporary pay cut" free text — out of scope for the deterministic engine, reserved for Phase 3's LLM layer. Phase 2 plans use a synthetic fixture instead of `request_06`'s exact numbers for testing the changes-adjusted eligibility path (02-planning).
- Phase 2's `determine_eligible_plans` computes eligibility twice — once from the raw forecast, once from a spending-changes-adjusted forecast (`apply_spending_changes_to_state` + `recompute_safety_with_changes`) — so `affordable_with_plan` via permitted spending changes is reachable and `requires_spending_changes` is a real (not hardcoded) discriminator in `rank_plans`' tie-break rule 2 (02-planning).
- `project_balance` reads a recurring category's sign from the `direction` column of its most recent settled row (not an amount-delta), matching `recurrence.py`'s recent-window amount-stability design so a step change (raise/rent increase) still forecasts at the correct sign and new level; recurring categories are fully excluded from the one-time event pass (their historical rows already fed `typical_amount`/`interval_days`) with an explicit per-date guard against double-counting a concrete row landing on a projected occurrence date (02-01).
- `compute_amount_safe_to_pay` is computed analytically (`min(daily_balances) - minimum_balance_to_keep`, clipped to `[0, requested_amount]`, floored to 2 decimals) rather than by brute-force search, enforcing the `0 <= amount_safe_to_pay <= requested_amount` invariant at the source (02-01).
- `determine_eligible_plans` tries the raw safety numbers first for `full_payment` and only falls back to changes-adjusted numbers if raw did not already qualify — never adds the same method twice, so a raw-safe candidate always strictly dominates an adjusted-safe one (02-02).
- `select_spending_changes` checks `expense_categories_to_protect` before flexibility/willingness/recurrence, and requires `financial_state.recurrence[category].is_recurring is True` (not merely a flexible label) — a one-time flexible purchase is never an eligible spending-change candidate, per problem_statement.md "Only recurring expenses marked as flexible may be changed" (02-02).
- `apply_spending_changes_to_state` deep-copies `FinancialState.recurrence` before patching (stop sets `is_recurring=False`, `reduce_to` sets `typical_amount`), so a simulated spending-change never mutates the original `FinancialState` (02-02).
- `rank_plans` implements the documented 6-step precedence as one explicit `sorted()` tuple key; `build_payment_plan_string` rounds-then-strips-zeros rather than using Python's `:g` format, which switches to scientific notation for large amounts like `15952906.67` (02-02).
- `derive_affordability_status` maps a `full_payment` `CandidatePlan` with `requires_spending_changes=True` to `affordable_with_plan` (not `affordable_now`), per problem_statement.md's `affordable_with_plan` definition; `build_output_row` always reports the raw (pre-spending-change) `amount_safe_to_pay`/`earliest_date_for_full_payment` in the output row, with changes-adjusted values only ever feeding `determine_eligible_plans` (02-03).
- `build_output_row` forces `earliest_date_for_full_payment` to the empty string whenever `affordability_status == "not_affordable"`, even if a raw earliest-date value exists in isolation (e.g. a user profile that does not accept `full_payment` at all) — fixed a bug affecting 8/250 rows in the first full-dataset run (02-03).

## Notes

- Deadline: 2026-09-13T18:00:00+05:30. Time is the binding constraint.
- GSD ceremony deliberately minimized per user choice (fast lightweight setup, no research/questioning agents) — see `.planning/PROJECT.md` Key Decisions.
- Local Ollama confirmed running at session start; models available: qwen2.5vl, gemma4, gemma4:e4b, llama3.2:3b.
- `code/dataio` package complete and tested (12/12 unittest passing): loaders, fx conversion, blank-amount resolution, `build_request_bundle()`. See `.planning/phases/01-data-layer-financial-state-reconstruction/01-01-SUMMARY.md`.
- `code/state` package complete and tested (19/19 unittest passing, 31/31 combined with dataio): cash-state classification, recurrence detection, message/image amendment extraction, conflict resolution, `build_financial_state(request_id)`. Verified against all 250 requests.csv rows with zero exceptions. See `.planning/phases/01-data-layer-financial-state-reconstruction/01-02-SUMMARY.md`.
- `code/forecast` package complete and tested (10/10 unittest passing, 41/41 combined with dataio+state): `project_balance` (90-day daily balance projection), `compute_amount_safe_to_pay`, `compute_earliest_date_for_full_payment`. Verified against all 250 requests.csv rows with zero exceptions and the `0 <= amount_safe_to_pay <= requested_amount` invariant holding on every row. See `.planning/phases/02-forecasting-engine-plan-selection/02-01-SUMMARY.md`.
- `code/plan` package complete and tested (24/24 unittest passing, 65/65 combined with dataio+state+forecast): `determine_eligible_plans`/`CandidatePlan` (PLAN-01, including changes-adjusted full_payment eligibility), `select_spending_changes`/`apply_spending_changes_to_state`/`recompute_safety_with_changes` (PLAN-04), `rank_plans`/`select_best_plan`/`build_payment_plan_string` (PLAN-02/PLAN-03). See `.planning/phases/02-forecasting-engine-plan-selection/02-02-SUMMARY.md`.
- `code/output` package complete and tested (8/8 unittest passing, 73/73 combined with dataio+state+forecast+plan): `build_output_row`/`derive_affordability_status` (single-request pipeline assembly) and `run_all_requests`/`write_output_csv` (full-dataset run and writer). `dataset/output.csv` regenerated with 250 real rows, exact column order, zero invariant violations (0 <= amount_safe_to_pay <= requested_amount, valid enum membership for affordability_status/recommended_payment_method for all rows). See `.planning/phases/02-forecasting-engine-plan-selection/02-03-SUMMARY.md`.
- Phase 1 complete. Phase 2 complete (3/3 plans: forecasting engine, plan eligibility/ranking, output assembly). `dataset/output.csv` has real deterministic predictions for all 250 requests with a placeholder `decision_explanation` marked for Phase 3's LLM replacement. Next: Phase 3 (LLM Integration, Local Ollama).
