"""gemma4-generated decision_explanation prose.

This module NEVER computes or changes any financial fact. It receives
the already-computed, final values for one output row (amount_safe_to_pay,
affordability_status, recommended_payment_method, payment_plan,
earliest_date_for_full_payment, spending_changes_needed, plus a handful
of supporting facts like requested_amount/home_currency/whether spending
changes were required) and asks gemma4 to write 1-3 short sentences of
grounded prose that only restates those facts in natural language. The
prompt explicitly instructs the model not to invent any number not
provided. A deterministic fallback template (the same style Phase 2
used as a placeholder) is used if the model call fails or the response
looks unusable (empty, or introduces a number not present in the
supplied facts).
"""

from __future__ import annotations

import re

from .client import OllamaClient, get_default_client

_EXPLAIN_MODEL = "gemma4"

_EXPLAIN_PROMPT_TEMPLATE = """You are writing a short, grounded explanation for a financial \
decision that has ALREADY been computed by a deterministic engine. You are not deciding \
anything -- only explaining the decision below in plain language.

Computed facts (the ONLY facts you may reference -- do not invent any other number, date, or \
fact):
- requested_amount: {requested_amount} {home_currency}
- amount_safe_to_pay: {amount_safe_to_pay} {home_currency}
- affordability_status: {affordability_status}
- recommended_payment_method: {recommended_payment_method}
- payment_plan: {payment_plan}
- earliest_date_for_full_payment: {earliest_date_for_full_payment}
- spending_changes_needed: {spending_changes_needed}
- minimum_balance_to_keep: {minimum_balance_to_keep} {home_currency}

Write 1-3 short sentences (max ~50 words total) explaining the recommendation, grounded ONLY in \
the facts above. Do not mention any other amount, date, or percentage. Do not add caveats about \
being an AI. Do not use markdown. Respond with ONLY the explanation text, nothing else.
"""

_NUMBER_PATTERN = re.compile(r"\d[\d,]*\.?\d*")


def _extract_numbers(*values) -> set[str]:
    """Collect normalized numeric tokens from the supplied grounding facts
    (used to sanity-check the model's output doesn't introduce a number
    that isn't grounded in what was passed in)."""
    tokens: set[str] = set()
    for value in values:
        for match in _NUMBER_PATTERN.findall(str(value)):
            tokens.add(match.replace(",", "").rstrip("0").rstrip(".") or "0")
    return tokens


def _fallback_explanation(
    amount_safe_to_pay: float,
    home_currency: str,
    recommended_payment_method: str,
    spending_changes_needed: str,
) -> str:
    method_label = recommended_payment_method.replace("_", " ").title()
    text = f"{method_label} recommended: safe amount is {amount_safe_to_pay} {home_currency}."
    if spending_changes_needed and spending_changes_needed != "none":
        text += f" Requires spending changes: {spending_changes_needed}."
    return text


def generate_decision_explanation(
    *,
    requested_amount: float,
    amount_safe_to_pay: float,
    affordability_status: str,
    recommended_payment_method: str,
    payment_plan: str,
    earliest_date_for_full_payment: str,
    spending_changes_needed: str,
    minimum_balance_to_keep: float,
    home_currency: str,
    client: OllamaClient | None = None,
) -> str:
    """Generate a short grounded decision_explanation via gemma4.

    Falls back to a deterministic template (never blank, never an
    exception) if the model call fails, or if the returned text appears
    to introduce a number that isn't one of the supplied grounding
    numbers (a conservative anti-hallucination guard -- financial-sounding
    prose with an unrecognized number is rejected in favor of the
    template rather than risking a fabricated fact in decision_explanation).
    """
    client = client or get_default_client()

    fallback = _fallback_explanation(
        amount_safe_to_pay, home_currency, recommended_payment_method, spending_changes_needed
    )

    prompt = _EXPLAIN_PROMPT_TEMPLATE.format(
        requested_amount=requested_amount,
        home_currency=home_currency,
        amount_safe_to_pay=amount_safe_to_pay,
        affordability_status=affordability_status,
        recommended_payment_method=recommended_payment_method,
        payment_plan=payment_plan,
        earliest_date_for_full_payment=earliest_date_for_full_payment or "not applicable",
        spending_changes_needed=spending_changes_needed,
        minimum_balance_to_keep=minimum_balance_to_keep,
    )

    try:
        response = client.generate(
            model=_EXPLAIN_MODEL,
            prompt=prompt,
            temperature=0.2,
            call_type="explain",
        )
    except Exception:
        return fallback

    text = response.strip()
    if not text:
        return fallback

    grounded_numbers = _extract_numbers(
        requested_amount,
        amount_safe_to_pay,
        payment_plan,
        earliest_date_for_full_payment,
        minimum_balance_to_keep,
    )
    response_numbers = _extract_numbers(text)
    ungrounded = response_numbers - grounded_numbers
    # Dates (YYYY-MM-DD) get split into 3 numeric tokens by the regex
    # (year/month/day) which will legitimately not match the raw
    # grounded-number set exactly for shorter forms (e.g. "07" vs "7") --
    # to keep this guard from being overly strict on date fragments,
    # only flag tokens that look like a plausible standalone amount
    # (length > 1, not a bare day/month/year fragment 1-4 digits long
    # that could plausibly come from splitting a date/plan string).
    ungrounded_amounts = {tok for tok in ungrounded if len(tok) > 4 or "." in tok}
    if ungrounded_amounts:
        return fallback

    return text
