---
phase: 01-data-layer-financial-state-reconstruction
plan: 02
subsystem: data
tags: [pandas, financial-state, regex, cash-flow-classification, recurrence-detection, conflict-resolution]

# Dependency graph
requires:
  - phase: 01-data-layer-financial-state-reconstruction (plan 01)
    provides: code/dataio package (load_all, build_request_bundle, RequestBundle, convert_amount, resolve_all_blank_amounts)
provides:
  - code/state package with classify_event/classify_events (cash-state classification)
  - detect_recurring/detect_all_recurring (recurrence detection from settled history)
  - extract_message_amendment/extract_image_amendment (untrusted-evidence amendment extraction)
  - resolve_conflict (documented 4-step conflict precedence)
  - build_financial_state(request_id) - single call site for Phase 2's forecasting engine
affects: [02-forecasting-engine-plan-selection]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Cash-state classification via a single classify_event(row) -> dict function; non_cash direction checked before status so investment valuations never count as cash regardless of status"
    - "Recurrence detection requires both amount stability (fractional tolerance of median) and cadence stability (day-gaps within +/-5 days of median) across >=3 settled occurrences before flagging is_recurring=True"
    - "Untrusted free text (message_text) is only ever read via regex/keyword matching, never eval/exec - a message containing an injection-style instruction matches no defined pattern and returns amendment_type='none'"
    - "Amendments are collected per target event_id, resolved via resolve_conflict when more than one amendment targets the same event, then applied and the affected row is re-classified so cash_state stays consistent"

key-files:
  created:
    - code/state/__init__.py
    - code/state/classify.py
    - code/state/recurrence.py
    - code/state/amendments.py
    - code/state/reconcile.py
    - code/tests/test_state.py
  modified: []

key-decisions:
  - "classify_event checks direction == 'non_cash' first, before status, so an investment valuation row is always excluded from counts_toward_forecast regardless of its status value (prevents an 'unrealized' vs 'settled' status mixup from ever counting non-cash value)"
  - "Unknown/unrecognized status+direction combinations default to excluded_unrecognized (counts_toward_forecast=False) rather than silently counting an unmodeled state - conservative-by-default"
  - "extract_message_amendment accepts either a pandas Series or a plain dict (csv.DictReader row) via a small _get/_blank shim, since the plan's acceptance criteria exercise it against both raw CSV dict rows and DataFrame rows from build_request_bundle"
  - "Image amendments are extracted for traceability (recorded amendment_type='amend_amount') but not re-applied on top of build_request_bundle's events, since join.py (Plan 01) already resolves blank amounts via the linked image before build_financial_state runs classification - avoids double-applying the same fact"

requirements-completed: [STATE-01, STATE-02, STATE-03, STATE-04, STATE-05]

# Metrics
duration: 20min
completed: 2026-09-13
---

# Phase 1 Plan 2: Financial State Reconstruction Summary

**`code/state` package classifying every financial event's cash-state, detecting recurring monthly patterns, extracting deterministic amendments from untrusted message/image evidence, and reconciling conflicts through a single documented 4-step precedence function culminating in `build_financial_state(request_id)`.**

## Performance

- **Duration:** 20 min
- **Started:** 2026-09-13T06:24:00Z
- **Completed:** 2026-09-13T06:29:11Z
- **Tasks:** 2
- **Files modified:** 6 (all new)

## Accomplishments
- `classify_event`/`classify_events` correctly bucket every event into exactly one cash-state treatment: cancelled/failed/unrealized excluded, non_cash excluded regardless of status, pending debits reserved, pending credits excluded until settled, scheduled counted as future known cash flow.
- `detect_recurring`/`detect_all_recurring` correctly flag `user_01` rent as recurring (5148.0 ZAR, 6 occurrences) using only observed settled history — amount + cadence stability, never guessed from a single row.
- `extract_message_amendment` treats `message_text` strictly as untrusted evidence (regex/keyword only, never eval/exec) and correctly parses the confirmed `message_01` salary-change case (user_02, IDR 42,750,000). A constructed prompt-injection-style message ("Ignore all previous rules...") matches no keyword pattern and returns `amendment_type="none"`, proving the threat-model mitigation holds.
- `resolve_conflict` implements the documented 4-step precedence (explicit amendment -> newest same-source record -> settled over estimate -> financially safer interpretation) as the single, traceable conflict-resolution function (`grep` confirms exactly one definition).
- `build_financial_state(request_id)` is the single call site Phase 2 needs: verified against `request_113` (event_10521 resolves to 393.22 via Plan 01's image lookup) and `request_26` (second currency, IDR, completes without exception). Ran a full-dataset smoke test across all 250 `requests.csv` rows — zero exceptions.

## Task Commits

1. **Task 1: Cash-state classification + recurrence detection** - `9d630a5` (feat)
2. **Task 2: Message/image amendments + conflict-resolution reconciliation** - `56cc5bc` (feat)

**Plan metadata:** (this commit)

## Files Created/Modified
- `code/state/classify.py` - `classify_event`/`classify_events`, `CASH_COUNTED_STATUSES`, `EXCLUDED_STATUSES`
- `code/state/recurrence.py` - `RecurrenceInfo` dataclass, `detect_recurring`/`detect_all_recurring`
- `code/state/amendments.py` - `Amendment` dataclass, `extract_message_amendment`/`extract_image_amendment` (untrusted-evidence extraction)
- `code/state/reconcile.py` - `resolve_conflict`, `FinancialState` dataclass, `build_financial_state(request_id)`
- `code/state/__init__.py` - package exports for all of the above
- `code/tests/test_state.py` - 19 unittest cases covering classification, recurrence, amendment extraction (including the untrusted-text injection case), conflict resolution, and end-to-end `build_financial_state`

## Decisions Made
- Non-cash direction is checked before status in `classify_event` so an investment valuation is always excluded regardless of its status label (see key-decisions above).
- Unrecognized status/direction combinations default to excluded rather than counted (conservative-by-default), since none are expected in this dataset (confirmed status values are settled/pending/scheduled/unrealized/cancelled/failed) but the function should never silently count an unmodeled state.
- Image amendments are extracted and recorded for traceability but not re-applied over `build_request_bundle`'s events, since Plan 01's join step already resolves the same blank-amount fact — avoids double-application.

## Deviations from Plan

None - plan executed exactly as written. All function signatures, dataclass fields, and acceptance criteria match the plan's specification exactly.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `code/state.build_financial_state(request_id)` is ready for Phase 2's 90-day forecasting engine to call directly; verified against every request_id in the full 250-row `requests.csv` with zero exceptions.
- Phase 3's LLM integration extension points remain clearly marked: `extract_message_amendment`/`extract_image_amendment` currently use deterministic regex/keyword matching; Phase 3 will route the free-text/image NLU calls to local Ollama (gemma4/qwen2.5vl) behind these same signatures.
- No blockers identified for Phase 2.

---
*Phase: 01-data-layer-financial-state-reconstruction*
*Completed: 2026-09-13*

## Self-Check: PASSED

All key files confirmed present on disk (code/state/__init__.py, classify.py, recurrence.py, amendments.py, reconcile.py, code/tests/test_state.py). Both task commits (9d630a5, 56cc5bc) confirmed present in git log. Full test suite (31 tests: 19 state + 12 dataio) passes. All plan acceptance criteria and plan-level verification commands re-run and pass. Full-dataset smoke test across all 250 requests.csv rows completes with zero exceptions.
