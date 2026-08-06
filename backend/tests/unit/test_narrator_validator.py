"""Number-hallucination guard tests.

These are the load-bearing tests for the narrator's honesty property.
If the validator ever misses a hallucinated number, prose the CA has
not vetted will land in front of the client — that violates the
positioning ("Niyam prepares and flags; the CA approves and advises").
"""
from __future__ import annotations

import pytest

from app.narrator.types import BlockerFact, NarrationFacts, NumberHallucination
from app.narrator.validator import (
    build_allowed_forms,
    extract_number_tokens,
    find_hallucinated,
    validate_output_blocks,
    _indian_grouped,
    _paise_to_rupees_int,
)


def _facts(**overrides) -> NarrationFacts:
    """Sensible-defaults factory. Every test overrides only what it needs."""
    base = dict(
        period="202607",
        return_type="GSTR1",
        firm_name="Acme CA",
        client_name="Beta Traders",
        sales_paise=1_00_00_000,   # ₹1,00,000
        purchases_paise=50_00_000,  # ₹50,000
        margin_paise=50_00_000,     # ₹50,000
        tax_paid_paise=25_00_000,   # ₹25,000
        tax_due_paise=30_00_000,    # ₹30,000
        itc_matched_paise=2_50_00_000,       # ₹2,50,000
        itc_probable_paise=1_50_00_000,      # ₹1,50,000
        itc_supplier_default_paise=43_00_000,  # ₹43,000
        itc_missing_entry_paise=1_20_00_000,   # ₹1,20,000
        itc_supplier_default_count=6,
        readiness_score=65,
        days_to_due=5,
        top_blockers=(
            BlockerFact(
                kind="supplier_default",
                owner="ca",
                description="ITC at risk from 6 suppliers",
                paise_impact=43_00_000,  # ₹43,000
            ),
        ),
        rule_pack_version="1.0.0",
    )
    base.update(overrides)
    return NarrationFacts(**base)


# ---------------------------------------------------------------------------
# Indian-grouping helper
# ---------------------------------------------------------------------------


class TestIndianGrouping:
    def test_short_numbers_pass_through(self) -> None:
        assert _indian_grouped("5") == "5"
        assert _indian_grouped("50") == "50"
        assert _indian_grouped("500") == "500"

    def test_thousand_grouping(self) -> None:
        assert _indian_grouped("43000") == "43,000"
        assert _indian_grouped("1000") == "1,000"

    def test_lakh_grouping(self) -> None:
        # 150000 → 1,50,000
        assert _indian_grouped("150000") == "1,50,000"
        # 43000000 → 4,30,00,000
        assert _indian_grouped("43000000") == "4,30,00,000"

    def test_crore_grouping(self) -> None:
        # 100000000 → 10,00,00,000 (10 crore)
        assert _indian_grouped("100000000") == "10,00,00,000"

    def test_negative(self) -> None:
        assert _indian_grouped("-43000") == "-43,000"


# ---------------------------------------------------------------------------
# Paise → rupees rounding
# ---------------------------------------------------------------------------


class TestPaiseToRupees:
    def test_whole_rupees(self) -> None:
        assert _paise_to_rupees_int(4_300_000) == "43000"

    def test_half_rupee_rounds_up(self) -> None:
        # 4300050 paise = ₹43000.50 → rounds to ₹43001
        assert _paise_to_rupees_int(4_300_050) == "43001"

    def test_sub_half_rounds_down(self) -> None:
        assert _paise_to_rupees_int(4_300_049) == "43000"

    def test_zero(self) -> None:
        assert _paise_to_rupees_int(0) == "0"

    def test_negative(self) -> None:
        assert _paise_to_rupees_int(-4_300_000) == "-43000"


# ---------------------------------------------------------------------------
# Extract number tokens
# ---------------------------------------------------------------------------


class TestExtractNumberTokens:
    def test_bare_number(self) -> None:
        assert extract_number_tokens("Score is 65") == ["65"]

    def test_currency_symbol_stripped(self) -> None:
        assert extract_number_tokens("You owe ₹43,000 to 6 suppliers.") == [
            "43000",
            "6",
        ]

    def test_percent(self) -> None:
        # "20%" tokenizes to just "20" — no % in the digit run.
        assert extract_number_tokens("Score climbed to 20%") == ["20"]

    def test_ordinal_becomes_digit(self) -> None:
        assert extract_number_tokens("Due on the 11th of August") == ["11"]

    def test_no_numbers(self) -> None:
        assert extract_number_tokens("A period with no numbers.") == []

    def test_empty(self) -> None:
        assert extract_number_tokens("") == []

    def test_multiple_run(self) -> None:
        assert extract_number_tokens("₹1,50,000 across 2 rows and 43,000 more") == [
            "150000",
            "2",
            "43000",
        ]


# ---------------------------------------------------------------------------
# Allowed forms — spot-check the set derived from a facts sheet
# ---------------------------------------------------------------------------


class TestBuildAllowedForms:
    def test_small_numbers_are_always_allowed(self) -> None:
        allowed = build_allowed_forms(_facts())
        # 0-100 inclusive — 100 is the readiness score scale ("out of 100"
        # in the narrator's own copy) so it lives in the allow-list.
        for i in range(0, 101):
            assert str(i) in allowed, f"{i} missing from allowed set"

    def test_money_values_included_as_rupee_ints(self) -> None:
        allowed = build_allowed_forms(_facts())
        # Sales ₹1,00,000 → "100000" in the set.
        assert "100000" in allowed
        # supplier_default ₹43,000 → "43000".
        assert "43000" in allowed
        # matched ITC ₹2,50,000 → "250000".
        assert "250000" in allowed

    def test_year_included(self) -> None:
        allowed = build_allowed_forms(_facts(period="202607"))
        assert "2026" in allowed

    def test_blocker_paise_included(self) -> None:
        allowed = build_allowed_forms(_facts())
        # Blocker has ₹43,000 impact → "43000".
        assert "43000" in allowed


# ---------------------------------------------------------------------------
# find_hallucinated — happy path + adversarial
# ---------------------------------------------------------------------------


class TestFindHallucinated:
    def test_allowed_number_passes(self) -> None:
        facts = _facts()
        allowed = build_allowed_forms(facts)
        out = find_hallucinated(
            "₹43,000 is at risk from 6 suppliers.", allowed
        )
        assert out == []

    def test_disallowed_number_rejected(self) -> None:
        facts = _facts()
        allowed = build_allowed_forms(facts)
        # ₹43,001 — one rupee off. Must be caught.
        out = find_hallucinated("₹43,001 is at risk.", allowed)
        assert out == ["43001"]

    def test_disallowed_large_number_rejected(self) -> None:
        facts = _facts()
        allowed = build_allowed_forms(facts)
        # 4,300 is NOT in facts (₹43,000 is, but not the plain 4300).
        # Numbers above the small-int ceiling must be in facts.
        out = find_hallucinated("Number is 4300.", allowed)
        assert out == ["4300"]

    def test_repeat_hallucination_dedupes_neighbours(self) -> None:
        facts = _facts()
        allowed = build_allowed_forms(facts)
        # "999" appears three times back-to-back — should surface once.
        out = find_hallucinated("999 and 999 and 999", allowed)
        assert out == ["999"]

    def test_large_but_allowed_year_passes(self) -> None:
        facts = _facts(period="202607")
        allowed = build_allowed_forms(facts)
        out = find_hallucinated("For the July 2026 period", allowed)
        assert out == []

    def test_indian_grouping_and_bare_forms_both_allowed(self) -> None:
        facts = _facts()
        allowed = build_allowed_forms(facts)
        assert find_hallucinated("₹43,000 total", allowed) == []
        assert find_hallucinated("43000 total", allowed) == []
        # Combined variants in one text.
        assert (
            find_hallucinated("₹43,000 (43000 paise-int)", allowed) == []
        )

    def test_days_past_due_absolute_form(self) -> None:
        facts = _facts(days_to_due=-5)
        allowed = build_allowed_forms(facts)
        assert find_hallucinated("5 days past due.", allowed) == []
        assert find_hallucinated("-5 days past due.", allowed) == []


# ---------------------------------------------------------------------------
# validate_output_blocks — end-to-end
# ---------------------------------------------------------------------------


class TestValidateOutputBlocks:
    def test_clean_output_passes(self) -> None:
        facts = _facts()
        validate_output_blocks(
            facts=facts,
            blocks={
                "page1_health": "Sales were ₹1,00,000 for the period.",
                "page1_tax_position": "Readiness stands at 65.",
                "page2_attention": "₹43,000 is at risk from 6 suppliers.",
                "page2_ask_your_ca": "",
            },
        )

    def test_hallucination_raises_with_block_context(self) -> None:
        facts = _facts()
        with pytest.raises(NumberHallucination) as exc:
            validate_output_blocks(
                facts=facts,
                blocks={
                    "page1_health": "Sales were ₹99,999 for the period.",
                    "page2_attention": "₹43,001 at risk.",
                    "page2_ask_your_ca": "",
                },
            )
        # Both blocks surface, each with their block-name prefix.
        offenders = set(exc.value.offending)
        assert "page1_health:99999" in offenders
        assert "page2_attention:43001" in offenders

    def test_allowed_sample_is_bounded(self) -> None:
        facts = _facts()
        with pytest.raises(NumberHallucination) as exc:
            validate_output_blocks(
                facts=facts,
                blocks={"page1_health": "Sales were ₹99,999"},
            )
        assert len(exc.value.allowed_sample) <= 20
