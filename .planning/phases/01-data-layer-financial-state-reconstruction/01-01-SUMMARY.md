---
phase: 01-data-layer-financial-state-reconstruction
plan: 01
subsystem: data-layer
tags: [pandas, csv, currency-conversion, vision-stub, data-join, unittest]

# Dependency graph
requires: []
provides:
  - "code/dataio package: load_all(), per-table CSV loaders, typed DataFrames"
  - "code/dataio/fx.py: build_rate_index/convert_amount deterministic currency conversion"
  - "code/dataio/vision_stub.py: resolve_blank_amount/resolve_all_blank_amounts with hardcoded 16-event lookup table + Phase 3 extension point"
  - "code/dataio/join.py: RequestBundle + build_request_bundle(request_id) single call site for per-request data"
affects: [01-02-PLAN.md (cash-state classification/recurrence/message-image amendments), Phase 2 (forecasting engine consumes build_request_bundle)]

# Tech tracking
tech-stack:
  added: [pandas 3.0.5]
  patterns:
    - "Loaders parse dates via pd.to_datetime and amounts via pd.to_numeric(errors=coerce) so blanks become NaN, never 0"
    - "fx.convert_amount tries direct (date, from, to) rate lookup, then inverse, then raises ValueError -- never fabricates a rate"
    - "vision_stub.py isolates blank-amount extraction behind _extract_amount_from_image with a '# PHASE 3 EXTENSION POINT' comment for the future Ollama qwen2.5vl swap-in"
    - "build_request_bundle accepts an optional pre-loaded `tables` dict to avoid reloading CSVs per request in later phases"

key-files:
  created:
    - code/__init__.py
    - code/evaluation/__init__.py
    - code/dataio/__init__.py
    - code/dataio/loaders.py
    - code/dataio/fx.py
    - code/dataio/vision_stub.py
    - code/dataio/join.py
    - code/tests/__init__.py
    - code/tests/test_dataio.py
    - .gitignore
  modified: []

key-decisions:
  - "Installed pandas via pip (no venv/requirements.txt existed yet) since PROJECT.md already committed to pandas as the stack choice -- treated as Rule 3 blocking-issue fix, not a new architectural decision"
  - "Added code/__init__.py and code/evaluation/__init__.py (previously absent) so `code.dataio`/`code.tests` import paths used throughout the plan's acceptance criteria resolve correctly"
  - "request_payment_options.csv has 790 data rows (verified via csv.reader and pandas), not 791 as stated in the plan's dataset facts -- used the verified count (790) in the loader test instead of the plan's stated figure"
  - "For event_3231 (Restaurant tax invoice), used the invoice's explicitly labeled 'Grand Total (RS): 8528' rather than the pre-rounding computed subtotal+tax of 8528.10"
  - "For event_9421 (handwritten pharmacy receipt), used the line-item sum (4543.00) which exactly matches the handwritten TOTAL field on close re-read, correcting an initial misread of '9' vs '4'"
  - "For event_1700 (grocery delivery order, image partially cropped), used 'Item Bill: INR 2854.00' since it is stated explicitly on the receipt and exactly equals the sum of all visible line items"

requirements-completed: [DATA-01, DATA-02, DATA-03, DATA-04]

# Metrics
duration: 30min
completed: 2026-09-13
---

# Phase 1 Plan 1: CSV Loaders, Currency Conversion, Blank-Amount Resolution & Per-Request Join Summary

**Built `code/dataio`: typed pandas loaders for all 7 dataset tables, dated exchange-rate currency conversion (direct/inverse lookup, raises on missing pairs), a hardcoded 16-event blank-amount resolution table extracted by manually reading every linked PNG, and `build_request_bundle(request_id)` joining request/profile/events/payment_options/messages/images with `amount_home_currency` populated.**

## Performance

- **Duration:** 30 min
- **Started:** 2026-09-13T05:51:00Z (approx, session start)
- **Completed:** 2026-09-13T06:21:50Z
- **Tasks:** 2
- **Files modified:** 11 created (loaders.py, fx.py, vision_stub.py, join.py, test_dataio.py, 3x `__init__.py`, .gitignore, tests/`__init__.py`)

## Accomplishments
- All 7 dataset tables (`financial_events`, `financial_profiles`, `requests`, `request_payment_options`, `exchange_rates`, `messages`, `images`) load into typed pandas DataFrames with verified row counts matching `wc -l - 1` / `csv.reader` ground truth, and blank `amount` cells are `NaN` (16 confirmed), never silently `0`.
- `convert_amount`/`build_rate_index` perform deterministic dated currency conversion with direct-pair lookup, inverse-pair fallback, and a `ValueError` raise (never a fabricated rate) on any missing `(date, from, to)` combination.
- All 16 blank-amount financial events (`event_253`, `event_1442`, `event_1545`, `event_1700`, `event_1786`, `event_3051`, `event_3231`, `event_4535`, `event_5170`, `event_6033`, `event_6859`, `event_7307`, `event_7941`, `event_9421`, `event_9806`, `event_10521`) resolve to a manually-verified, non-zero numeric amount extracted by reading each linked PNG under `dataset/media/images/`. `event_10521` reproduces the plan's confirmed ground-truth fact (393.22).
- `build_request_bundle(request_id)` is the single call site for Phase 2+: it looks up the request only in `requests.csv` (raises `KeyError` for sample-only IDs), resolves the user's blank-amount events, converts every cash event to the user's `home_currency`, and attaches the user's/request's payment options, messages, and images.

## Task Commits

Each task was committed atomically:

1. **Task 1: CSV loaders + currency conversion module** - `b1c98b6` (feat)
2. **Task 2: Blank-amount resolution stub + per-request join** - `a6435fb` (feat)

**Plan metadata:** (this commit, following SUMMARY write)

## Files Created/Modified
- `code/dataio/loaders.py` - Per-table CSV loaders + `load_all()`; explicit float/datetime dtype coercion; pipe-delimited profile fields split into lists
- `code/dataio/fx.py` - `build_rate_index`/`convert_amount`; direct/inverse dated rate lookup; raises `ValueError` on missing pair
- `code/dataio/vision_stub.py` - `resolve_blank_amount`/`resolve_all_blank_amounts`; hardcoded `_KNOWN_IMAGE_AMOUNTS` dict covering all 16 blank-amount events; `_extract_amount_from_image` marked as the Phase 3 Ollama vision extension point
- `code/dataio/join.py` - `RequestBundle` dataclass + `build_request_bundle(request_id, tables=None)`
- `code/dataio/__init__.py` - Exports `load_all`, `build_rate_index`, `convert_amount`
- `code/__init__.py`, `code/evaluation/__init__.py`, `code/tests/__init__.py` - Package scaffolding needed for `code.dataio`/`code.tests` imports (previously absent)
- `code/tests/test_dataio.py` - 12 unittest cases: loader row counts, blank-amount NaN check, fx direct/inverse/missing-pair/same-currency, full 16-event blank-amount resolution + no-mutation check + `event_10521==393.22`, `build_request_bundle` for `request_113`/`request_26`/`request_27` across INR/IDR/ZAR
- `.gitignore` - Added (previously absent); ignores `__pycache__/`, `*.pyc`, venv dirs, `.env`

## Decisions Made
- Installed `pandas` via pip since no venv/requirements.txt existed yet and PROJECT.md had already committed to pandas as the stack choice (Rule 3 blocking-issue fix, not a new architectural decision).
- Added missing `__init__.py` files at `code/`, `code/evaluation/`, and `code/tests/` so the plan's own acceptance-criteria import paths (`from code.dataio import load_all`, `python3 -m unittest code.tests.test_dataio`) resolve correctly.
- Corrected the plan's stated `request_payment_options.csv` row count (791) to the verified actual count (790 data rows, confirmed via both `csv.reader` and `pandas.read_csv`) in the loader test — used the verified figure rather than the plan's stated one.
- For each of the 15 non-confirmed blank-amount events, read the linked PNG directly and used the most explicit "Total"/"Grand Total"/"Balance Due"/"Net Pay" figure on the document, preferring the document's own stated total over any component sum when both were visible and they diverged in favor of an explicit label (e.g., event_3231 uses the invoice's stated "Grand Total (RS): 8528" over the pre-rounding 8528.10 subtotal+tax figure).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Installed missing pandas dependency**
- **Found during:** Task 1 (CSV loaders)
- **Issue:** No Python environment had pandas installed; no venv/requirements.txt existed in the repo. `from code.dataio import load_all` would fail immediately on `import pandas`.
- **Fix:** Ran `python3 -m pip install pandas`, which pulled pandas 3.0.5 (numpy/python-dateutil already present).
- **Files modified:** None (system Python site-packages only; not tracked in git)
- **Verification:** `python3 -c "import pandas"` succeeds; full test suite passes.
- **Committed in:** N/A (dependency install, not a file change)

**2. [Rule 3 - Blocking] Added missing `__init__.py` package markers**
- **Found during:** Task 1 (CSV loaders) — before writing any acceptance-criteria commands
- **Issue:** `code/__init__.py` and `code/evaluation/__init__.py` did not exist. The plan's own acceptance criteria (`from code.dataio import load_all`, `python3 -m unittest code.tests.test_dataio`) require `code` to be a regular package for reliable `unittest` discovery.
- **Fix:** Created empty `code/__init__.py`, `code/evaluation/__init__.py`, and `code/tests/__init__.py`.
- **Files modified:** `code/__init__.py`, `code/evaluation/__init__.py`, `code/tests/__init__.py`
- **Verification:** `python3 -m unittest code.tests.test_dataio -v` runs and discovers all 12 tests.
- **Committed in:** `b1c98b6` (Task 1), `a6435fb` (Task 2, tests `__init__.py`)

**3. [Rule 1 - Bug] Corrected stated `request_payment_options.csv` row count**
- **Found during:** Task 1 (CSV loaders), pre-implementation verification
- **Issue:** The plan's dataset facts stated 791 rows for `request_payment_options.csv`; independent verification via `csv.reader` and `pandas.read_csv` both confirmed 790 data rows.
- **Fix:** Used the verified count (790) in the acceptance-criteria check and in `test_dataio.py`, rather than the plan's stated 791.
- **Files modified:** `code/tests/test_dataio.py`
- **Verification:** `len(tables["payment_options"])` == 790, matches independent `csv.reader` count.
- **Committed in:** `a6435fb`

**4. [Rule 3 - Blocking] Added `.gitignore`**
- **Found during:** Task 1, before first commit
- **Issue:** No `.gitignore` existed; `__pycache__/` directories were appearing as untracked files after running tests, which would otherwise get committed or clutter `git status`.
- **Fix:** Added a minimal `.gitignore` covering `__pycache__/`, `*.pyc`, venv directories, and `.env`.
- **Files modified:** `.gitignore`
- **Verification:** `git status --short` no longer shows `__pycache__/` as untracked after running tests.
- **Committed in:** `b1c98b6`

---

**Total deviations:** 4 auto-fixed (3 blocking, 1 bug/data-correction)
**Impact on plan:** All deviations were necessary to make the plan's own acceptance criteria executable and correct. No scope creep — no functionality was added beyond what Task 1/Task 2 specified.

## Issues Encountered

- **Image amount extraction ambiguity (image_14, event_9421):** The handwritten pharmacy receipt's TOTAL field was initially ambiguous between "4593" and "4543" due to handwriting style. Resolved by re-reading the image at full resolution and cross-checking against the sum of the itemized line items (1500+724+796+550+303+670 = 4543), which matched the "4543" reading exactly. Used 4543.00 as the grounded, internally-consistent value.
- **Image amount ambiguity (image_07, event_3231):** The restaurant tax invoice shows both a computed "Total: 8528.10" (subtotal + taxes) and a separately stated "Grand Total (RS): 8528" (rounded). Used the explicitly labeled Grand Total (8528) as the authoritative document-stated figure.
- No blocking issues remain; all 12 tests and all plan/task-level acceptance criteria pass.

## User Setup Required

None - no external service configuration required. (Ollama/vision integration is explicitly deferred to Phase 3 per the plan; Phase 1 only needed the extension point wired, which is done via `_extract_amount_from_image`.)

## Next Phase Readiness

- `code/dataio` is fully functional and tested: `build_request_bundle(request_id)` is ready for Phase 2 (forecasting engine) and for 01-02-PLAN.md (cash-state classification, recurrence detection, message/image amendments, conflict resolution) to build directly on top of.
- All 16 blank-amount events resolve without exception; `resolve_all_blank_amounts` will not crash when 01-02/Phase 2 run it over the full dataset.
- No blockers. Ready for `01-02-PLAN.md`.

---
*Phase: 01-data-layer-financial-state-reconstruction*
*Completed: 2026-09-13*

## Self-Check: PASSED

All 10 key files verified present on disk; both task commits (`b1c98b6`, `a6435fb`) verified in git log; full test suite (12 tests) re-run and passed.
