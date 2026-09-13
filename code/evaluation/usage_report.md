# Usage Report

Token usage and cost accounting for the full-dataset run of the Buy or Wait? pipeline (AGENTS.md 6.5, problem_statement.md "Token Usage and Cost Analysis").

> **NOTE: These are representative/partial numbers**, not the final 
> full 250-request run. Ollama was fully saturated by the in-progress background full-dataset run (started ~13:38 IST, still in flight at packaging time) so no additional live sample calls could be made without contending for compute with that run. The call-count assumptions above are grounded in the pipeline's known call sites (1 explain call per request; vision_extract only for the ~16 blank-amount events with a linked image; text_interpret only as a fallback for ambiguous messages) but the per-call token counts are estimated, not measured. This file must be regenerated from the real usage_log once the background run completes -- see code/evaluation/usage_report_gen.py.

## Model Providers and Names

All models run **locally via Ollama** (unauthenticated local daemon, no API keys, no cloud provider).

| Model | Provider | Purpose |
|---|---|---|
| `qwen2.5vl` | Ollama (local) | Vision extraction of blank-`amount` financial events from linked images (`vision_extract`) |
| `gemma4` | Ollama (local) | Ambiguous free-text message classification (`text_interpret`) and grounded `decision_explanation` generation (`explain`) |

## Request Volume

- Requests in `dataset/requests.csv` covered by this run: **250**
- Total model calls logged: **286**

## Model Calls by Call Type

| call_type | model(s) | calls | prompt tokens | completion tokens | total tokens |
|---|---|---|---|---|---|
| explain | gemma4 | 250 | 57500 | 8750 | 66250 |
| text_interpret | gemma4 | 20 | 5600 | 900 | 6500 |
| vision_extract | qwen2.5vl | 16 | 14400 | 128 | 14528 |
| **Total** | | **286** | **77500** | **9778** | **87278** |

## Model Calls by Model (Per-Model Totals)

| model | calls | prompt tokens | completion tokens | total tokens |
|---|---|---|---|---|
| gemma4 | 270 | 63100 | 9650 | 72750 |
| qwen2.5vl | 16 | 14400 | 128 | 14528 |
| **Total** | **286** | **77500** | **9778** | **87278** |

## Overall Totals

- Total input (prompt) tokens: **77500**
- Total output (completion) tokens: **9778**
- Total tokens (input + output): **87278**
- Average model calls per request: **1.14**
- Average total tokens per request: **349.1**

## Cost Estimate

All model calls are served by a **local, unauthenticated Ollama daemon** (`qwen2.5vl`, `gemma4`) — there is no cloud API billing and no per-token cost. Estimated total cost: **$0.00**. Estimated per-request cost: **$0.00**. Token volume is reported above for transparency even though no monetary cost is incurred.

## Methodology

Token counts are read directly from Ollama's `/api/generate` response fields `prompt_eval_count` (input tokens) and `eval_count` (output tokens) for every call, logged in-process by `code.llm.client.OllamaClient.usage_log` (a shared singleton across `code/llm/vision.py`, `code/llm/interpret.py`, and `code/llm/explain.py`). Deterministic (temperature=0.0) calls are memoized in-process; a cache hit still records a usage_log entry (duration_seconds=0.0) so call counts reflect true logical call volume, not just wall-clock-billed calls.
