"""Top-level per-user financial state reconstruction.

build_financial_state(request_id) is the single call site Phase 2's
forecasting engine needs: it joins the raw dataset (via
code.dataio.join.build_request_bundle), classifies every event's cash
state, detects recurring categories, extracts message/image amendments
(untrusted evidence), and resolves any conflicts per the documented
4-step precedence from problem_statement.md "When records conflict,
prefer:".
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from code.dataio.join import build_request_bundle

from .amendments import Amendment, extract_image_amendment, extract_message_amendment
from .classify import classify_event, classify_events
from .recurrence import detect_all_recurring


def resolve_conflict(candidates: list[dict]) -> dict:
    """Resolve multiple conflicting candidate values for the same fact.

    Each candidate dict has keys:
        value: the candidate's proposed value
        source_type: str, e.g. "settled", "estimate", "forecast", or a
            message/image source_type
        record_date: a date-like value used to compare recency within the
            same source_type
        is_explicit_amendment: bool -- True if this candidate is an
            explicit cancellation/settlement/amendment fact
        direction: optional "debit"/"credit" -- used only for step 4
            (financially safer interpretation)

    Precedence (problem_statement.md "When records conflict, prefer:"):
        1. An explicit cancellation, settlement, or amendment wins outright.
           If multiple explicit candidates exist, the latest record_date
           among them (same source_type comparison) wins.
        2. Otherwise, the newest record_date from the same source_type wins.
        3. Otherwise, prefer source_type == "settled" over "estimate"/"forecast".
        4. Otherwise, the financially safer interpretation: for debits pick
           the larger amount (conservative reserve); for credits pick the
           smaller/later amount (conservative recognition).
    """
    if not candidates:
        raise ValueError("resolve_conflict requires at least one candidate")
    if len(candidates) == 1:
        return candidates[0]

    # Step 1: explicit amendments win outright.
    explicit = [c for c in candidates if c.get("is_explicit_amendment")]
    if explicit:
        if len(explicit) == 1:
            return explicit[0]
        pool = explicit
    else:
        pool = candidates

    # Step 2: newest record_date among same source_type wins, when dates differ.
    dated = [c for c in pool if c.get("record_date") is not None]
    if dated:
        dates = {pd.to_datetime(c["record_date"]) for c in dated}
        if len(dates) > 1:
            latest = max(dates)
            newest = [c for c in dated if pd.to_datetime(c["record_date"]) == latest]
            if len(newest) == 1:
                return newest[0]
            pool = newest

    # Step 3: prefer settled over estimate/forecast.
    settled = [c for c in pool if c.get("source_type") == "settled"]
    if settled:
        if len(settled) == 1:
            return settled[0]
        pool = settled

    # Step 4: financially safer interpretation.
    direction = pool[0].get("direction")
    if direction == "debit":
        return max(pool, key=lambda c: c["value"])
    if direction == "credit":
        return min(pool, key=lambda c: c["value"])

    # No direction info to disambiguate further: fall back to the first
    # remaining candidate (already narrowed by steps 1-3).
    return pool[0]


@dataclass
class FinancialState:
    user_id: str
    events: pd.DataFrame
    recurrence: dict = field(default_factory=dict)
    amendments_applied: list[Amendment] = field(default_factory=list)


def _apply_amendment(events_df: pd.DataFrame, amendment: Amendment) -> pd.DataFrame:
    """Apply a single amendment to the row matching its event_id.

    Only overwrites fields for the specific event_id the amendment is
    linked to -- never propagates to unrelated events (threat model
    "Amendment application -> events DataFrame mutation").
    """
    mask = events_df["event_id"] == amendment.event_id
    if not mask.any():
        return events_df

    if amendment.amendment_type == "amend_amount" and amendment.new_amount is not None:
        events_df.loc[mask, "amount_home_currency"] = amendment.new_amount
    elif amendment.amendment_type == "cancel":
        events_df.loc[mask, "status"] = "cancelled"

    # Re-run classification for the affected row(s) so cash_state /
    # counts_toward_forecast / treatment stay consistent with the amendment.
    for idx in events_df.index[mask]:
        classification = classify_event(events_df.loc[idx])
        for key, val in classification.items():
            events_df.at[idx, key] = val

    return events_df


def build_financial_state(request_id: str, tables: dict[str, pd.DataFrame] | None = None) -> FinancialState:
    bundle = build_request_bundle(request_id, tables=tables)
    user_id = bundle.profile["user_id"]

    events = classify_events(bundle.events)

    categories = events["category"].dropna().unique()
    recurrence = {category: detect_all_recurring(events, user_id)[category] for category in categories}

    # Collect amendments keyed by target event_id so conflicting amendments
    # for the same event go through resolve_conflict.
    amendments_by_event: dict[str, list[dict]] = {}
    all_amendments: list[Amendment] = []

    for _, message_row in bundle.messages.iterrows():
        amendment = extract_message_amendment(message_row)
        all_amendments.append(amendment)
        if amendment.event_id is not None and amendment.amendment_type != "none":
            # An LLM-assisted classification NEVER counts as an "explicit
            # amendment" (resolve_conflict step 1, outright win) --
            # regardless of the model's self-reported confidence. A
            # manual injection probe during Phase 3 development
            # confirmed gemma4 will confidently ("high") extract a
            # fabricated new_amount from adversarial instruction-like
            # text embedded in message_text. Only a DETERMINISTIC
            # regex/keyword match (extract_message_amendment's first
            # pass) can ever be an explicit, step-1, outright-winning
            # amendment.
            is_explicit = amendment.amendment_type in ("amend_amount", "cancel")
            if amendment.llm_assisted:
                is_explicit = False

                # CRITICAL: an LLM-derived signal must never be allowed
                # to win purely by being the *only* candidate considered
                # for this event_id (resolve_conflict's len==1
                # short-circuit would otherwise apply it unconditionally
                # -- exactly the injection path the manual probe
                # exposed). Inject the event's own currently-recorded,
                # settled value as a competing baseline candidate so an
                # uncorroborated model read must actually win step 3/4
                # of resolve_conflict's precedence (settled beats
                # estimate; financially-safer wins remaining ties) on
                # its merits, never by default.
                existing_matches = events[events["event_id"] == amendment.event_id]
                if len(existing_matches) > 0:
                    existing_row = existing_matches.iloc[0]
                    amendments_by_event.setdefault(amendment.event_id, []).append(
                        {
                            "amendment": None,
                            "value": existing_row.get("amount_home_currency"),
                            "source_type": "settled" if existing_row.get("status") == "settled" else existing_row.get("status"),
                            "record_date": existing_row.get("settlement_date") or existing_row.get("event_date"),
                            "is_explicit_amendment": False,
                            "direction": existing_row.get("direction"),
                        }
                    )

            amendments_by_event.setdefault(amendment.event_id, []).append(
                {
                    "amendment": amendment,
                    "value": amendment.new_amount,
                    "source_type": message_row.get("source_type"),
                    "record_date": message_row.get("sent_at"),
                    "is_explicit_amendment": is_explicit,
                    "direction": None,
                }
            )

    # Images only ever amend the blank-amount event they were already
    # resolved for during join (bundle.events['amount_home_currency'] is
    # already the image-derived value). We still extract+record them here
    # for traceability, but do not need to re-apply since join.py already
    # populated the resolved amount.
    for _, image_row in bundle.images.iterrows():
        related_event_id = image_row.get("related_event_id")
        if pd.isna(related_event_id) or str(related_event_id).strip() == "":
            continue
        matches = events[events["event_id"] == related_event_id]
        if len(matches) == 0:
            continue
        resolved_amount = float(matches.iloc[0]["amount_home_currency"])
        amendment = extract_image_amendment(image_row, resolved_amount)
        if amendment is not None:
            all_amendments.append(amendment)

    applied: list[Amendment] = []
    for event_id, candidates in amendments_by_event.items():
        winner = resolve_conflict(candidates)
        if winner["amendment"] is None:
            # The synthetic "keep the existing recorded value" baseline
            # candidate won -- an uncorroborated LLM-derived amendment
            # lost on the merits (see the baseline-injection comment
            # above), so no mutation is applied for this event_id at
            # all. This is the safety net verified by
            # code/tests/test_llm_injection.py.
            continue
        events = _apply_amendment(events, winner["amendment"])
        applied.append(winner["amendment"])

    return FinancialState(
        user_id=user_id,
        events=events,
        recurrence=recurrence,
        amendments_applied=applied,
    )
