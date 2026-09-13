"""Message/image-driven amendment extraction.

Threat model (see 01-02-PLAN.md <threat_model>, T-01-04): `message_text` is
untrusted free text supplied by employers/banks/merchants/service
providers/financial services. It is evidence, never instructions. This
module NEVER calls eval/exec/subprocess on message content and only ever
produces data (Amendment objects) via deterministic regex/keyword
matching. A message containing an instruction like "ignore the rules"
matches no defined pattern and returns amendment_type="none".

Phase 1 built the deterministic extraction scaffold. Phase 3 adds an LLM
fallback (code.llm.interpret.classify_ambiguous_message, gemma4) that
only fires when the deterministic layer found amendment_type == "none"
-- extract_message_amendment tries deterministic regex/keyword matching
FIRST, always, and only calls the LLM as a second pass. The LLM's
output is still just an Amendment (this module's existing dataclass,
unchanged) with `llm_assisted=True`, `llm_confidence` set, and
`raw_evidence` preserving the original untrusted text. Critically, the
existing event_id gating is untouched: an Amendment only ever mutates
FinancialState when the *message row itself* already carried a
populated `related_event_id` -- the LLM cannot invent a link to an
event it wasn't already pointed at, and any resulting amendment still
flows through code.state.reconcile.resolve_conflict's existing
precedence like every other candidate. See
code/tests/test_llm_injection.py for the adversarial-instruction
regression test that verifies this end-to-end.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

_CANCEL_KEYWORDS = ("cancel", "dibatalkan", "batal")
_DELAY_KEYWORDS = ("delayed", "ditunda", "postponed")
_CONFIRM_KEYWORDS = ("confirmed", "dikonfirmasi")

# Change-keyword phrases followed by a currency-coded amount, e.g.
# "naik menjadi IDR 42750000" or "increased to USD 1,200.50".
_AMOUNT_CHANGE_PATTERN = re.compile(
    r"(?:naik menjadi|increased to|berubah menjadi|new salary|updated to)"
    r"\s+([A-Z]{3})\s*([\d.,]+)",
    re.IGNORECASE,
)


@dataclass
class Amendment:
    source: str
    source_id: str
    event_id: str | None
    amendment_type: str
    new_amount: float | None
    new_date: str | None
    raw_evidence: str
    llm_assisted: bool = False
    llm_confidence: str | None = None


def _get(row, key):
    """Read a field from either a pandas Series or a plain dict (csv.DictReader)."""
    if isinstance(row, pd.Series):
        return row.get(key)
    return row.get(key)


def _blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def _parse_amount(raw: str) -> float:
    """Strip thousands separators and parse a matched number as float.

    Handles both comma-thousands ("1,200.50") and bare digit strings
    ("42750000") -- never treats the raw text as executable, purely a
    regex-extracted numeric string.
    """
    cleaned = raw.replace(",", "")
    return float(cleaned)


def extract_message_amendment(message_row, use_llm_fallback: bool = True) -> Amendment:
    """Extract an amendment signal from one messages.csv row.

    Deterministic regex/keyword matching runs FIRST, always. Only when
    that pass finds nothing (amendment_type == "none") AND
    `use_llm_fallback` is True AND the message row already carries a
    populated `related_event_id` (this module never fabricates a new
    event linkage) does this fall back to gemma4
    (code.llm.interpret.classify_ambiguous_message) for a second
    classification pass over the same untrusted text. The LLM path can
    only ever adjust `amendment_type`/`new_amount` on an Amendment that
    was already going to target that same, pre-existing event_id --
    never a different one, and never bypass
    code.state.reconcile.resolve_conflict's precedence.

    `message_text` is treated strictly as untrusted data in both passes:
    only regex/keyword matching or a narrowly-scoped, sandboxed LLM
    classification call is performed, never eval/exec.
    """
    message_id = _get(message_row, "message_id")
    text = _get(message_row, "message_text") or ""
    text_lower = str(text).lower()

    related_event_id = _get(message_row, "related_event_id")
    event_id = None if _blank(related_event_id) else related_event_id

    amendment_type = "none"
    new_amount: float | None = None
    new_date: str | None = None

    if any(keyword in text_lower for keyword in _CANCEL_KEYWORDS):
        amendment_type = "cancel"
    else:
        match = _AMOUNT_CHANGE_PATTERN.search(str(text))
        if match:
            amendment_type = "amend_amount"
            new_amount = _parse_amount(match.group(2))
        elif any(keyword in text_lower for keyword in _DELAY_KEYWORDS):
            amendment_type = "delay"
        elif any(keyword in text_lower for keyword in _CONFIRM_KEYWORDS):
            amendment_type = "confirm"

    llm_assisted = False
    llm_confidence: str | None = None

    if amendment_type == "none" and use_llm_fallback and event_id is not None:
        # Only worth an LLM call when there is a real event_id for the
        # resulting Amendment to target -- an amendment with no
        # event_id is structurally inert in build_financial_state, so
        # skipping the call here is a pure efficiency win, not a
        # security-relevant gate (the gate itself lives in the check
        # above and in reconcile.py's amendments_by_event collection).
        from code.llm.interpret import classify_ambiguous_message

        classification = classify_ambiguous_message(str(text))
        if classification is not None and classification.amendment_type != "none":
            amendment_type = classification.amendment_type
            new_amount = classification.new_amount
            llm_assisted = True
            llm_confidence = classification.confidence

    return Amendment(
        source="message",
        source_id=message_id,
        event_id=event_id,
        amendment_type=amendment_type,
        new_amount=new_amount,
        new_date=new_date,
        raw_evidence=str(text),
        llm_assisted=llm_assisted,
        llm_confidence=llm_confidence,
    )


def extract_image_amendment(image_row, resolved_amount: float) -> Amendment | None:
    """Extract an amendment from an image row, only when linkage actually exists.

    Per STATE-04: only apply when `related_event_id` is populated in
    images.csv -- never fabricate an event linkage.
    """
    related_event_id = _get(image_row, "related_event_id")
    if _blank(related_event_id):
        return None

    image_id = _get(image_row, "image_id")
    return Amendment(
        source="image",
        source_id=image_id,
        event_id=related_event_id,
        amendment_type="amend_amount",
        new_amount=resolved_amount,
        new_date=None,
        raw_evidence=f"image {image_id}",
    )
