"""Real qwen2.5vl vision extraction for blank-amount financial events.

Replaces code.dataio.vision_stub's Phase-1 hardcoded lookup table as the
PRIMARY path. The lookup table is retained as a safety-net fallback only
(if the live model call fails or returns an unparseable/implausible
value) -- never as the primary source of truth, per the Phase 3 task
scope.
"""

from __future__ import annotations

import base64
import re

from .client import OllamaClient, get_default_client

_VISION_MODEL = "qwen2.5vl"

_EXTRACT_PROMPT = (
    "You are looking at a financial document image (receipt, invoice, "
    "payslip, or bill). Extract the single total/net monetary amount "
    "payable or received, as shown on the document (e.g. 'Total', "
    "'Grand Total', 'Net Pay', 'Balance Due', 'Amount Received'). "
    "Respond with ONLY the numeric amount: digits and at most one "
    "decimal point, no currency symbol, no thousands separators, no "
    "words, no explanation. Example valid response: 4365000.00"
)

_NUMERIC_PATTERN = re.compile(r"-?\d[\d,]*\.?\d*")


def _parse_numeric_response(raw: str) -> float | None:
    """Extract the first plausible numeric token from the model's text
    response. Returns None if nothing numeric-looking is found."""
    cleaned = raw.strip()
    match = _NUMERIC_PATTERN.search(cleaned)
    if not match:
        return None
    token = match.group(0).replace(",", "")
    try:
        value = float(token)
    except ValueError:
        return None
    return value


def _is_plausible_amount(value: float) -> bool:
    """Sanity bound: a financial-document amount should be strictly
    positive and within a plausible magnitude (rules out obvious
    mis-reads like '0' or a wildly out-of-range hallucination)."""
    return 0 < value < 1_000_000_000


def extract_amount_via_vision(
    image_path: str, client: OllamaClient | None = None
) -> float | None:
    """Call qwen2.5vl against the image at `image_path` and return the
    extracted numeric amount, or None if the call failed or produced an
    unparseable/implausible result (caller decides on fallback)."""
    client = client or get_default_client()

    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    response = client.generate(
        model=_VISION_MODEL,
        prompt=_EXTRACT_PROMPT,
        images=[image_b64],
        temperature=0.0,
        call_type="vision_extract",
    )

    value = _parse_numeric_response(response)
    if value is None or not _is_plausible_amount(value):
        return None
    return value
