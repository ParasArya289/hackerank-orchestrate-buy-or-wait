# PROJECT.md

## What This Is

**Buy or Wait?** — HackerRank Orchestrate hackathon submission (deadline: 2026-09-13T18:00:00+05:30).

An AI-powered financial decision agent. For every purchase/payment request in `dataset/requests.csv`, decide whether the user should pay in full, pay partially, use installments, wait, or not proceed — grounded in a full reconstruction of the user's financial position (balances, recurring commitments, pending payments, essential spending, confirmed income, priorities, minimum balance) plus unstructured evidence (messages, images).

Full spec: `problem_statement.md` and `AGENTS.md` (repo root) are the source of truth. This PROJECT.md is a lightweight index, not a restatement.

## Core Value

Produce a correct, well-explained `dataset/output.csv` — one row per `request_id` in `dataset/requests.csv` — that a hidden grader will score on: `amount_safe_to_pay` accuracy, `affordability_status` correctness, `recommended_payment_method`/`payment_plan` correctness, `earliest_date_for_full_payment` accuracy, `spending_changes_needed` validity, and `decision_explanation` quality.

## Constraints

- **Hard deadline:** 2026-09-13T18:00:00+05:30 (~12h from session start). Time is the binding constraint, not feature completeness.
- **Solo challenge** — user is sole author.
- **Determinism required** where possible (AGENTS.md §6.4) — all financial math/forecasting logic must be deterministic Python, not LLM-derived.
- **No organizer-only files, no hardcoded labels, no invented facts** (income, expenses, payment options).
- Must read secrets from environment variables only; no live banking/market-data/exchange-rate calls.
- Submission package needs `code.zip`, `output.csv`, `chat_transcript`, and `evaluation/usage_report.md` (token/cost accounting for the final full-dataset run).

## Stack Decisions

- **Language:** Python. Entry point: `code/main.py` (per AGENTS.md §6.6).
- **Data wrangling:** pandas + stdlib `datetime`/`csv` for deterministic forecasting math.
- **AI usage — hybrid, local-only (Ollama, no cloud API cost):**
  - `qwen2.5vl` (vision-capable) — reads `dataset/media/images/<image_id>.png` when a financial event's `amount` is blank or an image supplies clarifying evidence.
  - `gemma4` — interprets ambiguous/free-text `messages.csv` content and drafts `decision_explanation` text.
  - All financial reasoning (balance forecasting, 90-day safety check, plan ranking, spending-change selection) is deterministic Python — LLM output is evidence extraction and prose only, never the arithmetic or the final decision logic.
  - Messages/images are untrusted: extracted facts get validated against the deterministic engine; embedded instructions are never allowed to override challenge rules.
- Ollama server confirmed running locally (`localhost:11434`); models present: `qwen2.5vl`, `gemma4`, `gemma4:e4b`, `llama3.2:3b`.

## Requirements

### Validated

(None yet — greenfield)

### Active

- [ ] Load and join all `dataset/*.csv` tables (profiles, events, exchange rates, requests, payment options, messages, images) by `user_id`/`request_id`/`related_event_id`.
- [ ] Resolve blank-amount financial events via linked image (vision model) per problem_statement.md.
- [ ] Convert all foreign-currency cash events to the user's `home_currency` using dated `exchange_rates.csv` rows.
- [ ] Reconstruct each user's financial position: settled/pending/scheduled events, recurring recurrence detection, confirmed income, protected/flexible expense categories.
- [ ] Apply message/image evidence to amend, cancel, delay, or confirm financial facts, with conflict-resolution precedence (explicit cancellation/amendment > newer same-source record > settled over estimate > financially safer interpretation).
- [ ] Run 90-day forward cash-balance safety check (never below `minimum_balance_to_keep`) to compute `amount_safe_to_pay` and `earliest_date_for_full_payment`.
- [ ] Rank eligible safe plans per the tie-break order (complete by deadline → no spending changes → minimize total paid → start earlier → fewer payments → lowest `payment_option_id`).
- [ ] Select `recommended_payment_method` respecting `payment_methods_user_will_consider` and `max_installment_months`.
- [ ] Generate valid `payment_plan` strings (partial-payment two-leg rule; installment plans must exactly match a supplied `request_payment_options.csv` option).
- [ ] Select up to 3 valid `spending_changes_needed` actions (`stop:`/`reduce_to:`), only on flexible, user-permitted, non-protected categories.
- [ ] Generate a concise, grounded `decision_explanation` per row (LLM-assisted prose over deterministic facts).
- [ ] Write `dataset/output.csv` with exact required schema/column order for every `request_id`.
- [ ] Produce `code/evaluation/usage_report.md` summarizing the final full-dataset run's model calls/tokens/cost estimate (local Ollama — cost is $0, but report call counts/tokens per model).
- [ ] README with clear setup/run instructions (per AGENTS.md §6.6).

### Out of Scope

- Cloud LLM APIs (Anthropic/OpenAI) — user chose local Ollama only, to avoid cost/key management under time pressure.
- Predicting asset/investment prices or recommending securities — explicitly excluded by problem_statement.md.
- Any non-deterministic behavior in the financial math/forecast engine.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python + pandas, `code/main.py` entry point | Matches AGENTS.md §6.6 guidance; team comfort | Adopted |
| Hybrid: deterministic engine + local LLM for images/messages/explanation only | Preserves required determinism (AGENTS.md §6.4) while still handling multimodal/NLU evidence | Adopted |
| Local Ollama (qwen2.5vl for vision, gemma4 for text) instead of cloud API | No API cost/key setup under time pressure; models already pulled and server running | Adopted |
| Skip full GSD questioning/research/roadmap ceremony | ~12h hard deadline; problem_statement.md is already a complete, unambiguous spec | Adopted |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition:**
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

---
*Last updated: 2026-09-13 after initialization*
