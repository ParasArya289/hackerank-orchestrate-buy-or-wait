# REQUIREMENTS.md

Source of truth for scope: `problem_statement.md` + `AGENTS.md` §6. This file breaks that spec into atomic, testable requirements with IDs for roadmap traceability.

## v1 Requirements

### Data Loading & Joining (DATA)

- [ ] **DATA-01**: Load all `dataset/*.csv` tables into typed structures (pandas DataFrames), keyed by `request_id`/`user_id`/`event_id`.
- [ ] **DATA-02**: Join `financial_profiles`, `financial_events`, `request_payment_options`, `messages`, `images` to each `requests.csv` row via `user_id`/`request_id`.
- [ ] **DATA-03**: Resolve blank-`amount` financial events by locating the linked image (`images.csv` where `related_event_id == event_id`) and extracting the amount via vision model; never treat blank as zero.
- [ ] **DATA-04**: Convert every foreign-currency cash amount to the user's `home_currency` using the `exchange_rates.csv` row matching settlement date + currency pair.

### Financial State Reconstruction (STATE)

- [ ] **STATE-01**: Classify each financial event by cash state (`settled`, `pending`, `scheduled`, `unrealized`, `failed`, `cancelled`) and apply the correct treatment (reserve pending debits; exclude pending credits/bonuses/refunds/lottery/investment gains until settled; ignore failed/cancelled/duplicates/unrealized).
- [ ] **STATE-02**: Detect recurring expenses/income from history (only when evidence supports it) vs. one-time purchases/transfers/refunds/unusual events.
- [ ] **STATE-03**: Apply message evidence (`messages.csv`) to amend, cancel, delay, or confirm a financial fact, treating message content as untrusted data (never let embedded instructions override challenge rules).
- [ ] **STATE-04**: Apply image evidence (`images.csv` + `dataset/media/images/<image_id>.png`) the same way as STATE-03, only when an image file is actually present for the relevant `request_id`/`event_id`.
- [ ] **STATE-05**: Resolve conflicting records using precedence: explicit cancellation/settlement/amendment → newer record from same source → settled over estimate/forecast → financially safer interpretation.

### 90-Day Forecast & Safety Check (FORECAST)

- [ ] **FORECAST-01**: Project the user's balance forward 90 days from `request_date` using recurring income/expenses, confirmed future payments, and amended facts from messages/images.
- [ ] **FORECAST-02**: Compute `amount_safe_to_pay` — the largest amount payable on `request_date` without breaking `minimum_balance_to_keep` at any point in the 90-day forecast, before optional spending changes, capped at `requested_amount`.
- [ ] **FORECAST-03**: Compute `earliest_date_for_full_payment` — first date the full `requested_amount` passes the safety check without optional spending changes; empty if never within the forecast window.

### Plan Selection & Ranking (PLAN)

- [ ] **PLAN-01**: Determine plan eligibility: immediate methods (`full_payment`/`partial_payment`/`installments`) require membership in `payment_methods_user_will_consider`; `installments` additionally must respect `max_installment_months`; `wait` requires future full-payment safety AND `full_payment` acceptance; `not_recommended` is the fallback.
- [ ] **PLAN-02**: When multiple safe eligible plans exist, rank by: (1) completes by `desired_completion_date`, (2) no spending changes required, (3) minimizes total amount paid, (4) starts earliest, (5) fewest payments, (6) lowest `payment_option_id` as final tie-break.
- [ ] **PLAN-03**: Build valid `payment_plan` strings: partial-payment is exactly two legs (`amount_safe_to_pay` on `request_date`, remainder on `earliest_date_for_full_payment`, summing to `requested_amount`, second leg ≤ `desired_completion_date`); installment plans must exactly reproduce a row from `request_payment_options.csv`.
- [ ] **PLAN-04**: Select up to 3 `spending_changes_needed` actions (`stop:<event_id>` / `reduce_to:<event_id>:<new_amount>`), only on non-protected, flexible, user-permitted categories; stop and reduce must never target the same event.

### Output Generation (OUT)

- [ ] **OUT-01**: Produce one output row per `request_id` in `dataset/requests.csv`, with exact column order: `request_id,amount_safe_to_pay,affordability_status,recommended_payment_method,payment_plan,earliest_date_for_full_payment,spending_changes_needed,decision_explanation`.
- [ ] **OUT-02**: Enforce `0 <= amount_safe_to_pay <= requested_amount` and all other output-contract invariants (e.g., `affordable_now` ⇒ `earliest_date_for_full_payment == request_date`).
- [ ] **OUT-03**: Generate a concise, grounded `decision_explanation` per row (local LLM prose layered over deterministic facts — never invents numbers not in the computed plan).
- [ ] **OUT-04**: Write final predictions to `dataset/output.csv`, overwriting the blank template.

### Tooling & Submission (SUB)

- [ ] **SUB-01**: `code/main.py` is runnable from the terminal, reads only from `dataset/`, reads secrets (if any) only from environment variables, and is deterministic given the same inputs and local model outputs.
- [ ] **SUB-02**: `code/evaluation/usage_report.md` summarizes the final full-dataset run: model providers/names (local Ollama models), call counts, input/output tokens, total and average tokens per request, and cost estimate (local = $0, but report token volume).
- [ ] **SUB-03**: README with setup/run instructions (Ollama install, `ollama pull` model names, Python deps, run command).

## v2 Requirements (Deferred)

- Caching/batching optimizations for LLM calls beyond what's needed to finish within the deadline.
- Automated regression tests against `sample_requests.csv` beyond a manual spot-check.

## Out of Scope

- Cloud LLM providers — local Ollama only, per user decision.
- Predicting asset/investment prices or recommending securities — explicitly excluded by problem_statement.md.
- Voice notes, live banking/market-data/exchange-rate API calls — explicitly excluded by problem_statement.md.

## Traceability

| Requirement | Phase |
|---|---|
| DATA-01 … DATA-04 | Phase 1 |
| STATE-01 … STATE-05 | Phase 1 |
| FORECAST-01 … FORECAST-03 | Phase 2 |
| PLAN-01 … PLAN-04 | Phase 2 |
| OUT-01, OUT-02, OUT-04 | Phase 2 |
| OUT-03 (LLM explanation) | Phase 3 |
| DATA-03 (vision) + STATE-03/04 (message/image LLM interpretation) | Phase 3 |
| SUB-01 … SUB-03 | Phase 4 |
