# Buy or Wait? — Solution README

This is the solution submitted for the HackerRank Orchestrate "Buy or Wait?"
challenge. It is a deterministic financial-decision engine (Python) with a
thin local-LLM layer (Ollama) for image-based amount extraction, ambiguous
free-text message interpretation, and natural-language explanation
generation.

## Architecture

```
code/
├── main.py            Entry point (python3 code/main.py)
├── dataio/            CSV loading, table joins, currency conversion,
│                       blank-amount resolution (vision-first, hardcoded
│                       lookup as safety-net fallback)
├── state/              Cash-state classification, recurrence detection,
│                       message/image amendment extraction, conflict
│                       resolution -> build_financial_state()
├── forecast/           90-day daily balance projection, amount_safe_to_pay
│                       / earliest_date_for_full_payment computation
├── plan/               Plan eligibility, spending-change selection,
│                       ranking, payment_plan string building
├── output/             Per-request output row assembly + full-dataset
│                       writer (writer.py: run_all_requests / write_output_csv)
├── llm/                Local Ollama client + vision.py (qwen2.5vl) +
│                       interpret.py (gemma4) + explain.py (gemma4)
├── evaluation/         usage_report.md + usage_report_gen.py (this report's
│                       generator, re-run against the real usage_log to
│                       regenerate it from any full run)
└── tests/              unittest suite (74 tests at last full run)
```

## Requirements

- Python 3.10+ (developed against 3.13)
- `pandas` (`pip install pandas`)
- A local [Ollama](https://ollama.com) daemon, unauthenticated, no API keys
- Two Ollama models pulled locally:

```bash
ollama pull qwen2.5vl
ollama pull gemma4
```

No cloud LLM providers are used. No secrets/API keys are required anywhere
in this solution; `OLLAMA_HOST` may optionally be set as an environment
variable to point at a non-default local Ollama host, but defaults to
`http://localhost:11434`.

## Setup

```bash
# from the repository root
pip install pandas

# start Ollama (if not already running) and pull the two models used
ollama serve &        # or use the Ollama desktop app / launchd service
ollama pull qwen2.5vl
ollama pull gemma4
```

## Run

From the repository root:

```bash
python3 code/main.py
```

This loads every table in `dataset/`, builds one output row per
`request_id` in `dataset/requests.csv` (in file order), writes the result
to `dataset/output.csv` (overwriting the blank template), and finally
verifies the output-contract invariants (row count, `0 <= amount_safe_to_pay
<= requested_amount`, valid enum membership for `affordability_status` /
`recommended_payment_method`).

Equivalent alternative entry point (does the same thing without the
progress/invariant wrapper):

```bash
python3 -m code.output.writer
```

A full run over all 250 requests takes roughly 2-2.5 hours on a single
consumer GPU/CPU-only machine, dominated by local LLM latency (~30-60s per
request across the vision/interpret/explain calls that fire for that
request). Deterministic (temperature=0.0) LLM calls are memoized in-process,
so re-running the same message/image content does not re-pay full latency
on a second pass within the same process.

## Running Tests

```bash
python3 -m unittest discover -s code/tests
```

## Regenerating the Usage Report

`code/evaluation/usage_report.md` is generated from
`code.llm.client.OllamaClient.usage_log`, the shared in-process record of
every Ollama call made during a run (model, call_type, prompt/completion
token counts read from Ollama's own `prompt_eval_count`/`eval_count`
response fields, call duration). To regenerate it after a full run:

```python
from code.output.writer import run_all_requests, write_output_csv
from code.llm.client import get_default_client
from code.evaluation.usage_report_gen import write_usage_report

rows = run_all_requests("dataset")
write_output_csv(rows, "dataset/output.csv")
write_usage_report(get_default_client().usage_log, num_requests=len(rows))
```

## Determinism

Given the same `dataset/` inputs and the same local model outputs, the
pipeline is deterministic: all LLM calls used for financial-state
reconstruction and classification run at `temperature=0.0`; the only
`temperature=0.2` call is the prose-only `decision_explanation` generator,
which never affects any computed financial number (a deterministic
template fallback is used whenever the model's response would introduce an
ungrounded number, or the call fails). All non-LLM computation (forecasting,
plan eligibility/ranking, invariant enforcement) is pure/deterministic
Python.
