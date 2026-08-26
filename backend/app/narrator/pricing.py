"""Narrator pricing config — paise per million tokens, per model.

TODO-VERIFY-PRICING (owner must resolve before shipping):
    Both the USD list prices below and ``USD_TO_PAISE_FX`` are opinions
    that drift. Provider pricing pages and the INR/USD spot rate must be
    reconciled at ``PRICING_EFFECTIVE_FROM`` and every subsequent price
    change. Nothing here is authoritative — treat each entry as a
    working assumption pending owner confirmation.

Why this module exists (Phase 1.4, P3_BUILD_PROMPT §3.1.4):
    Money is integer paise everywhere in Niyam. Providers quote in USD.
    We keep the USD list prices AND the FX rate we assumed AS explicit
    config so a stale-price bug is a visible mismatch (USD_TO_PAISE_FX
    doesn't match today's spot; PRICING_EFFECTIVE_FROM is old) rather
    than a hidden float rounding.

Design:
    * :data:`MODEL_PRICE_USD_PER_M` — provider list prices, USD per
      million tokens, in the same shape the old service.py constant
      used. Extend by adding a new key; unknown model → cost_paise NULL
      so the aggregation surfaces it as ``any_unpriced=true``.
    * :data:`USD_TO_PAISE_FX` — integer paise per USD used to convert.
      Uses paise so no float is stored; the conversion multiplies by
      this integer and divides using ceiling division, so we never
      under-report cost.
    * :func:`estimate_cost_paise` — returns int paise or None. Callers
      write it verbatim to ``narrator_call_log.cost_paise``. NULL is
      the honest signal for unpriced models; do not coerce it to 0.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, TypedDict


class ModelPrice(TypedDict):
    """USD per million tokens, per token kind (Anthropic-style buckets).

    Gemini's pricing table maps onto the same buckets — cache_read /
    cache_creation numbers reflect Gemini CachedContent semantics even
    where the adapter does not yet exercise them.
    """

    input: float
    output: float
    cache_read: float
    cache_creation: float


# When these numbers were last reviewed. If today is materially after
# this date, the numbers are stale — the aggregation endpoint surfaces
# the mismatch alongside every cost figure.
#
# TODO-VERIFY-PRICING: owner to bump this on every provider price change
# or FX reset.
PRICING_EFFECTIVE_FROM: datetime = datetime(2026, 8, 26, tzinfo=timezone.utc)


# Integer paise per one USD. Kept as an integer so no float is ever
# stored — the conversion multiplies then uses ceiling division. This
# is a working assumption at PRICING_EFFECTIVE_FROM; the spot rate
# drifts daily.
#
# TODO-VERIFY-PRICING: owner to reset this on any material FX move.
USD_TO_PAISE_FX: int = 8_400  # ~₹84.00 / USD as of 2026-08


# Provider list prices in USD per million tokens.
#
# TODO-VERIFY-PRICING: owner to reconcile against provider pricing
# pages on every announced change. Do not soften — an over-report is
# better than an under-report for the CA's cost dashboard.
MODEL_PRICE_USD_PER_M: dict[str, ModelPrice] = {
    # Anthropic Opus 4.7
    "claude-opus-4-7": {
        "input": 15.00,
        "output": 75.00,
        # Cache read is 10x cheaper than fresh input.
        "cache_read": 1.50,
        # Cache creation is a one-time cost, ~25% premium over fresh input.
        "cache_creation": 18.75,
    },
    # Anthropic Sonnet 4.6
    "claude-sonnet-4-6": {
        "input": 3.00,
        "output": 15.00,
        "cache_read": 0.30,
        "cache_creation": 3.75,
    },
    # Anthropic Haiku 4.5 — current default (settings.narrator_model)
    "claude-haiku-4-5-20251001": {
        "input": 1.00,
        "output": 5.00,
        "cache_read": 0.10,
        "cache_creation": 1.25,
    },
    # Google Gemini 2.5 Flash — cheapest workable option for the
    # narrator task. Free tier available with different privacy terms
    # (see docs/narrator-security.md §Provider policies).
    "gemini-2.5-flash": {
        "input": 0.35,
        "output": 1.05,
        # Gemini caching is opt-in via CachedContent objects and not
        # wired in the current adapter. Set the cache prices anyway so
        # a future caching-enabled build gets accurate numbers.
        "cache_read": 0.09,
        "cache_creation": 1.00,
    },
    # Google Gemini 2.5 Pro — higher quality vernacular, still cheap
    "gemini-2.5-pro": {
        "input": 1.25,
        "output": 5.00,
        "cache_read": 0.31,
        "cache_creation": 1.25,
    },
}


def estimate_cost_paise(model: str, usage: dict) -> Optional[int]:
    """Compute per-call cost in integer paise, or None if unpriced.

    ``usage`` follows Anthropic's ``response.usage`` shape:
    ``input_tokens``, ``output_tokens``, ``cache_read_input_tokens``,
    ``cache_creation_input_tokens``. Anthropic reports these as
    disjoint counts (fresh input = input - cache_read - cache_creation).

    Returns ``None`` when ``model`` is not in
    :data:`MODEL_PRICE_USD_PER_M` — the caller writes NULL into
    ``narrator_call_log.cost_paise`` so the aggregation surfaces the
    row as unpriced rather than as free.

    Never returns a float. Uses ceiling division on the paise-scaled
    intermediate so a truncation cannot under-report cost.
    """
    prices = MODEL_PRICE_USD_PER_M.get(model)
    if prices is None:
        return None
    it = int(usage.get("input_tokens") or 0)
    ot = int(usage.get("output_tokens") or 0)
    crt = int(usage.get("cache_read_input_tokens") or 0)
    cct = int(usage.get("cache_creation_input_tokens") or 0)
    if it == 0 and ot == 0 and crt == 0 and cct == 0:
        # Mock adapter path — no LLM call, no cost.
        return 0
    fresh_input = max(0, it - crt - cct)
    # USD-per-million × tokens × paise-per-USD → paise, all scaled up
    # by 1_000_000 to stay in integer arithmetic until the final divide.
    #
    # Each price bucket is a float provider quote. We multiply out then
    # ceiling-divide by 1_000_000 so residual sub-paise never under-
    # reports cost.
    scaled_paise_micro = (
        fresh_input * prices["input"]
        + ot * prices["output"]
        + crt * prices["cache_read"]
        + cct * prices["cache_creation"]
    ) * USD_TO_PAISE_FX
    # Ceiling division on the float (float → int with round-up).
    return int(-(-scaled_paise_micro // 1_000_000))


def estimate_cost_usd(model: str, usage: dict) -> Optional[float]:
    """Legacy USD estimate kept for the /narrator dashboard's display.

    The stored source-of-truth is ``cost_paise`` (integer). This helper
    exists so an existing display that shows dollars keeps working; new
    code should read ``cost_paise`` and format paise → rupees at the
    edge. Returns None for unpriced models to preserve the honest
    signal.
    """
    prices = MODEL_PRICE_USD_PER_M.get(model)
    if prices is None:
        return None
    it = int(usage.get("input_tokens") or 0)
    ot = int(usage.get("output_tokens") or 0)
    crt = int(usage.get("cache_read_input_tokens") or 0)
    cct = int(usage.get("cache_creation_input_tokens") or 0)
    fresh_input = max(0, it - crt - cct)
    total_micro = (
        fresh_input * prices["input"]
        + ot * prices["output"]
        + crt * prices["cache_read"]
        + cct * prices["cache_creation"]
    )
    return round(total_micro / 1_000_000, 6)
