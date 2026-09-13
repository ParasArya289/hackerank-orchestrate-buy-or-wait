# Phase 4: Full-Dataset Run, Packaging & Submission Prep Summary

Direct execution, no PLAN.md, per explicit user instruction to skip planning ceremony for Phases 3-4 given the hackathon deadline (2026-09-13T18:00:00+05:30).

**One-liner:** Built `code/main.py` entry point, a reusable `usage_report.md` generator grounded in `OllamaClient.usage_log`, and the solution README; assembled `code.zip`; packaged against the last known-good `dataset/output.csv` snapshot because two competing background full-dataset runs were still in flight and had not produced a final file by the time this phase wrapped up.

## What Was Built

1. **`code/main.py`** -- thin entry point per AGENTS.md 6.6 / SUB-01. Calls `run_all_requests("dataset", progress_callback=...)` then `write_output_csv(...)`, prints progress every 10 requests, and runs `code.output.writer._verify_invariants()` at the end. Runnable as `python3 code/main.py`.
2. **`code/evaluation/usage_report_gen.py`** -- reusable generator that turns a list of `UsageRecord` (or a JSON dump of the same shape) into `code/evaluation/usage_report.md`: model providers/names, calls/tokens by `call_type` and by `model`, overall totals, average tokens per request, and an explicit $0.00 cost statement (local Ollama, no billing). Exposes `write_usage_report(usage_log, num_requests, ...)` for direct use after any future full run.
3. **`code/evaluation/usage_report.md`** -- generated content, but populated with representative/estimated numbers, not measured ones (see Known Limitation below).
4. **`code/README.md`** -- solution-specific setup and run instructions (Ollama install, `ollama pull qwen2.5vl` / `ollama pull gemma4`, `pip install pandas`, `python3 code/main.py`, test command, usage-report regeneration snippet, determinism notes).
5. **`code.zip`** -- assembled at repo root, containing `code/` (all packages: dataio, state, forecast, plan, output, llm, evaluation, tests, main.py, README.md), excluding `__pycache__`/`.pyc`. Does not include `dataset/` (organizer-provided input files, not meant to be redistributed by the participant) or the root `output.csv`/`chat_transcript`, which are submitted as separate top-level files per problem_statement.md's submission table.

## Key Decisions

- Did not touch `dataset/output.csv`. Two background writers were found running concurrently against the same file path: PID 18804 (started 13:40:24, the legitimate run referenced in this phase's task brief) and PID 27493 (started 17:07:11, an unexpected duplicate racing the same output file and contending for Ollama compute with the legitimate run). Both were still alive at the end of this phase (218/250 and in-progress respectively). Per the explicit instruction not to interfere with the legitimate background run, and because killing a process was blocked by the auto-mode permission classifier ("Interfere With Workloads"), neither process was terminated. This is flagged below as an action item for the user.
- No live Ollama sample calls were made for the usage report. A single trivial gemma4 "Say OK" test call timed out after 25s because Ollama was fully saturated by the in-flight background run(s). Adding more load would have further slowed the legitimate run, so no further live-call attempts were made.
- `usage_report.md` was generated from grounded estimates, not measurements, and is explicitly labeled as provisional inside the file itself. Call-count assumptions are grounded in real code-path facts (1 `explain` call per request always fires per `code/output/assemble.py`; `vision_extract` only for the ~16 blank-amount events with a linked image, matching STATE.md's Phase 1 finding and `images.csv`'s 16 data rows; `text_interpret` only as a deterministic-layer fallback for ambiguous messages, conservatively estimated). Per-call token counts are rough ~4 chars/token estimates against the actual prompt templates in `code/llm/{explain,interpret,vision}.py` -- not measured token counts.
- `code.zip` excludes `dataset/`. problem_statement.md's submission table lists `code.zip`, `output.csv`, and `chat_transcript` as three separate deliverables, with `output.csv` submitted independently -- `dataset/` itself is organizer-provided and not called out as something the participant must redistribute inside `code.zip`.

## Final State / What Still Needs To Be Redone

As of session end (~17:22 IST, ~38 minutes before the 18:00 deadline):

- Background run PID 18804 (the legitimate ~13:40-started full run): 218/250 requests complete, ETA approximately 32 minutes from its last log line -- i.e., projected to finish very close to or slightly after the 18:00 deadline.
- Background run PID 27493 (duplicate, started 17:07): still running, actively racing PID 18804 for the same `dataset/output.csv` output path and contending for Ollama compute. Not killed (blocked by the permission system, see above).
- `dataset/output.csv` on disk is still the 13:04 snapshot (250 rows, valid per Phase 3's completed run) -- neither background process has overwritten it yet as of this summary.
- `code/evaluation/usage_report.md` reflects estimated, not measured, numbers.
- `code.zip` was built against the current repo state (code only, no dataset), which is final and does not need to change regardless of which background run finishes.

**Action items for the user, in priority order:**

1. Decide which background process should "win." If PID 18804 finishes first, its output is authoritative and more advanced. If PID 27493 finishes first (or overwrites mid-write), it may still be valid but was working from a contended, slower Ollama backend -- consider manually killing PID 27493 (`kill 27493`) to stop the race and let PID 18804 finish cleanly.
2. Once one run reaches "DONE" and `dataset/output.csv` is confirmed stable (unchanging file size/mtime for a few seconds, ideally cross-checked against a "Wrote 250 rows..." log line), regenerate `code/evaluation/usage_report.md` with real numbers:
   ```python
   from code.llm.client import get_default_client
   from code.evaluation.usage_report_gen import write_usage_report
   write_usage_report(get_default_client().usage_log, num_requests=250)
   ```
   Note: the two background runs as launched do not expose their in-memory usage_log to this session (separate processes) -- the real usage_log will only be available if a fresh run is executed via `code/main.py` in a process this script can inspect, OR if one of the background scripts is modified in advance to dump `get_default_client().usage_log` to disk on completion. Given time constraints, this was not retrofitted into the already-running background jobs.
3. Re-zip `code.zip` after regenerating `usage_report.md` (from repo root: `rm -f code.zip && zip -r code.zip code -x "*/__pycache__/*" -x "*.pyc"`).
4. Confirm `dataset/output.csv` is the final, complete 250-row file before submitting it as the standalone `output.csv` deliverable.

## Self-Check

- `code/main.py` exists and parses (`ast.parse` succeeded). FOUND.
- `code/evaluation/usage_report_gen.py` exists, imported successfully, and was exercised in-process to produce `code/evaluation/usage_report.md` (3271 chars written). FOUND.
- `code/evaluation/usage_report.md` exists and contains the required sections (providers/names, call-type breakdown, per-model totals, overall totals, cost estimate, methodology) with an explicit provisional-data disclosure. FOUND.
- `code/README.md` exists with setup/run instructions matching `code/main.py`'s actual behavior. FOUND.
- `code.zip` exists at repo root (70099 bytes, 48 files, `code/` tree only, `__pycache__` excluded). FOUND.
- Commit eb2344b contains `code/main.py`, `code/evaluation/usage_report.md`, `code/evaluation/usage_report_gen.py`, `code/README.md`. Verified via `git show --stat`.

## Self-Check: PASSED
