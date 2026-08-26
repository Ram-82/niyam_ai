"""Unit tests for :mod:`app.narrator.pricing` — pure functions, no DB.

The narrator persists the paise cost value at call time; a mistake here
corrupts every downstream cost figure. Covers the invariants the
service depends on:

* Unknown model → None (honest "unpriced" signal for the aggregation).
* All-zero tokens → 0 paise (mock-adapter row with no LLM call).
* Known model with the Opus 4.7 list-price math (worked example matches
  the service integration test).
* Ceiling behaviour — sub-paise residual rounds UP so cost is never
  under-reported.
"""
from __future__ import annotations

import math

import pytest

from app.narrator import pricing


def test_unknown_model_returns_none() -> None:
    """None is the honest signal for 'this model is not in the pricing
    config'; the caller writes NULL to narrator_call_log.cost_paise and
    the /narrator/costs aggregation flags any_unpriced=true. Do not
    coerce to 0 — that would misread partial data as free."""
    result = pricing.estimate_cost_paise(
        "no-such-model-yet",
        {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    )
    assert result is None


def test_zero_tokens_returns_zero_paise_for_priced_model() -> None:
    """The mock adapter reports zero-or-None tokens on every call.
    A priced model with truly zero usage costs zero paise (not NULL) —
    NULL is reserved for 'unknown model', 0 for 'known model, no
    tokens'. Distinguishing the two matters for the aggregation."""
    result = pricing.estimate_cost_paise(
        "claude-opus-4-7",
        {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    )
    assert result == 0


def test_none_token_fields_treated_as_zero() -> None:
    """The service passes usage.dict() with Optional[int] fields that
    can be None on failed adapter calls. Callers must not need to
    coalesce; pricing.estimate_cost_paise treats None like 0."""
    result = pricing.estimate_cost_paise(
        "claude-opus-4-7",
        {
            "input_tokens": None,
            "output_tokens": None,
            "cache_read_input_tokens": None,
            "cache_creation_input_tokens": None,
        },
    )
    assert result == 0


def test_opus_4_7_math_matches_known_list_prices() -> None:
    """Verify the worked example the /narrator/costs integration test
    also asserts. Opus 4.7 prices ($/M): input=15, output=75,
    cache_read=1.50. For (input=1M, output=1M, cache_read=1M,
    cache_creation=0): fresh_input = 1M - 1M - 0 = 0, so USD cost =
    0*15 + 1*75 + 1*1.50 = $76.50. Paise cost = 76.5 × USD_TO_PAISE_FX,
    ceiling-rounded."""
    usd_cost_micro = (0 * 15 + 1_000_000 * 75 + 1_000_000 * 1.50)
    expected_paise = math.ceil(
        usd_cost_micro * pricing.USD_TO_PAISE_FX / 1_000_000
    )
    result = pricing.estimate_cost_paise(
        "claude-opus-4-7",
        {
            "input_tokens": 1_000_000,
            "output_tokens": 1_000_000,
            "cache_read_input_tokens": 1_000_000,
            "cache_creation_input_tokens": 0,
        },
    )
    assert result == expected_paise


def test_fresh_input_computed_from_total_minus_cache_columns() -> None:
    """Anthropic reports input_tokens, cache_read, cache_creation as
    disjoint counts. 'Fresh input' (the part billed at full input
    price) = input - cache_read - cache_creation. If cache_read alone
    exceeds input, fresh_input clamps at 0 rather than going negative."""
    # cache_read > input — fresh_input must clamp to 0, not go negative.
    result = pricing.estimate_cost_paise(
        "claude-opus-4-7",
        {
            "input_tokens": 100,
            "output_tokens": 0,
            "cache_read_input_tokens": 500,
            "cache_creation_input_tokens": 0,
        },
    )
    # fresh_input clamped to 0; only cache_read contributes.
    # 500 * 1.50 = 750 USD-micro; × 8400 = 6_300_000 paise-scaled;
    # / 1_000_000 (ceiling) = 7 paise (6.3, rounded up).
    scaled = 500 * 1.50 * pricing.USD_TO_PAISE_FX
    expected = math.ceil(scaled / 1_000_000)
    assert result == expected


def test_ceiling_never_underreports() -> None:
    """A sub-paise residual must round UP so cost is never
    under-reported. Truncation would let the CA see a lower number
    than they will actually be billed for; over-report is safe,
    under-report is not."""
    # Contrive a usage that produces a strict fractional paise. One
    # token of Haiku output at $5/M with FX ≈ 8400:
    # 1 * 5 * 8400 / 1_000_000 = 0.042 paise → ceils to 1.
    result = pricing.estimate_cost_paise(
        "claude-haiku-4-5-20251001",
        {
            "input_tokens": 0,
            "output_tokens": 1,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
        },
    )
    assert result is not None
    assert result >= 1  # Not truncated to 0.


@pytest.mark.parametrize(
    "model",
    [
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ],
)
def test_shipped_models_are_all_priced(model: str) -> None:
    """Every model id that appears in a running deployment as a
    default narrator_model must be present in MODEL_PRICE_USD_PER_M
    so it never silently produces an unpriced row. This is a
    regression fence — dropping a model from the config without
    updating the deployment surface will make it fail loudly here."""
    assert model in pricing.MODEL_PRICE_USD_PER_M
    row = pricing.MODEL_PRICE_USD_PER_M[model]
    for bucket in ("input", "output", "cache_read", "cache_creation"):
        assert bucket in row
        assert row[bucket] >= 0
