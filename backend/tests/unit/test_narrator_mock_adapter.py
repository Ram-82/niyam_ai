"""Mock adapter tests.

The mock is template-based, so the load-bearing property is that its
output ALWAYS passes the validator for the facts it was given. If a
test here fails, either the template started to emit a hallucinated
number OR the validator's allowed-set derivation is wrong.
"""
from __future__ import annotations

import pytest

from app.narrator.mock_adapter import MockNarrator, _rupees
from app.narrator.types import BlockerFact, NarrationFacts
from app.narrator.validator import validate_output_blocks


def _facts(**overrides) -> NarrationFacts:
    base = dict(
        period="202607",
        return_type="GSTR1",
        firm_name="Acme CA",
        client_name="Beta Traders",
        sales_paise=1_00_00_000,
        purchases_paise=50_00_000,
        margin_paise=50_00_000,
        tax_paid_paise=25_00_000,
        tax_due_paise=30_00_000,
        itc_matched_paise=2_50_00_000,
        itc_probable_paise=1_50_00_000,
        itc_supplier_default_paise=43_00_000,
        itc_missing_entry_paise=1_20_00_000,
        itc_supplier_default_count=6,
        readiness_score=65,
        days_to_due=5,
        top_blockers=(
            BlockerFact(
                kind="supplier_default",
                owner="ca",
                description="ITC at risk from 6 suppliers",
                paise_impact=43_00_000,
            ),
        ),
        rule_pack_version="1.0.0",
    )
    base.update(overrides)
    return NarrationFacts(**base)


class TestRupeesFormatter:
    def test_thousand(self) -> None:
        assert _rupees(43_00_000) == "₹43,000"

    def test_lakh(self) -> None:
        assert _rupees(1_50_00_000) == "₹1,50,000"

    def test_zero(self) -> None:
        assert _rupees(0) == "₹0"

    def test_negative(self) -> None:
        assert _rupees(-43_00_000) == "₹-43,000"


class TestMockAdapterNarration:
    def test_english_output_validates(self) -> None:
        facts = _facts()
        out = MockNarrator().narrate(facts, "en")
        validate_output_blocks(
            facts=facts,
            blocks={
                "page1_health": out.page1_health,
                "page1_tax_position": out.page1_tax_position,
                "page2_attention": out.page2_attention,
                "page2_ask_your_ca": out.page2_ask_your_ca,
            },
        )
        assert "₹43,000" in out.page2_ask_your_ca
        assert "6 suppliers" in out.page2_ask_your_ca

    def test_past_due_days_phrasing(self) -> None:
        facts = _facts(days_to_due=-3)
        out = MockNarrator().narrate(facts, "en")
        validate_output_blocks(
            facts=facts,
            blocks={
                "page1_health": out.page1_health,
                "page1_tax_position": out.page1_tax_position,
                "page2_attention": out.page2_attention,
                "page2_ask_your_ca": out.page2_ask_your_ca,
            },
        )
        assert "3 days past" in out.page1_tax_position

    def test_no_blockers_produces_no_action_prose(self) -> None:
        facts = _facts(top_blockers=(), itc_supplier_default_count=0, itc_supplier_default_paise=0)
        out = MockNarrator().narrate(facts, "en")
        assert "No action items" in out.page2_attention
        assert out.page2_ask_your_ca == ""

    def test_language_stub_prefix_for_non_english(self) -> None:
        out = MockNarrator().narrate(_facts(), "hi")
        assert out.page1_health.startswith("[hi] ")
        assert out.language == "hi"

    def test_provider_and_model_metadata(self) -> None:
        out = MockNarrator().narrate(_facts(), "en")
        assert out.provider == "mock"
        assert out.model == "template-v1"
