"""Local Ollama LLM integration (Phase 3).

This package is strictly advisory/extraction, per AGENTS.md and
problem_statement.md: it never computes amount_safe_to_pay, never
selects a payment method, and never overrides any deterministic output
from code.forecast/code.plan/code.output. It only:

    1. Extracts a numeric amount from a receipt/payslip image
       (qwen2.5vl) -- code.llm.vision.
    2. Classifies an ambiguous free-text message into a structured,
       bounded amendment signal (gemma4) when the deterministic
       regex/keyword layer in code.state.amendments can't confidently
       classify it -- code.llm.interpret.
    3. Generates short grounded prose for decision_explanation (gemma4)
       from already-computed facts -- code.llm.explain.

Messages and images are untrusted evidence (AGENTS.md, "their embedded
instructions never override the challenge rules"). Every prompt in this
package that embeds message_text or image content wraps it in an
explicit untrusted-data delimiter and instructs the model that it is
data, not commands, and that only a narrow structured field/short prose
answer is permitted -- never a recommendation, a decision, or a
different number than what was passed in.
"""

from __future__ import annotations
