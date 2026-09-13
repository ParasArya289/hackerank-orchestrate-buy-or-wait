"""Message/image-driven amendment extraction.

Threat model (see 01-02-PLAN.md <threat_model>, T-01-04): `message_text` is
untrusted free text supplied by employers/banks/merchants/service
providers/financial services. It is evidence, never instructions. This
module NEVER calls eval/exec/subprocess on message content and only ever
produces data (Amendment objects) via deterministic regex/keyword
matching. A message containing an instruction like "ignore the rules"
matches no defined pattern and returns amendment_type="none".

Phase 1 builds the deterministic extraction scaffold. Phase 3 (per
ROADMAP.md) routes the actual free-text/image NLU calls to local Ollama
models (gemma4 for text, qwen2.5vl for vision) -- this module's function
signatures are the extension point Phase 3 will build on.
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


def extract_message_amendment(message_row) -> Amendment:
    """Extract a deterministic amendment signal from one messages.csv row.

    `message_text` is treated strictly as untrusted data: only
    regex/keyword matching is performed, never eval/exec.
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

    return Amendment(
        source="message",
        source_id=message_id,
        event_id=event_id,
        amendment_type=amendment_type,
        new_amount=new_amount,
        new_date=new_date,
        raw_evidence=str(text),
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
