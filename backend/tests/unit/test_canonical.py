"""Unit tests for canonical normalization + content_hash.

These are the load-bearing rules that the reconciliation engine also uses
in step 5. If ``normalize_invoice_number`` regresses, ``INV-001`` and
``inv 1`` stop deduping — silently — and CAs see doubled invoices in the
register. Belt-and-braces tests below.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.ingestion.canonical import (
    CanonicalInvoice,
    normalize_invoice_number,
    paise_display,
    rupees_to_paise,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("INV-001", "INV1"),
        ("inv 1", "INV1"),
        ("0001", "1"),
        ("INV/0001", "INV1"),
        ("INV.001", "INV1"),
        ("  inv-001  ", "INV1"),
        ("A0000012345", "A12345"),
        ("0", "0"),  # never collapse to empty string
        ("", "0"),
    ],
)
def test_normalize_invoice_number(raw: str, expected: str) -> None:
    assert normalize_invoice_number(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("100.00", 10_000),
        ("100", 10_000),
        (100, 10_000),
        (100.005, 10_001),  # HALF_UP rounding
        ("0", 0),
        (None, 0),
        ("", 0),
        ("1234.56", 123_456),
    ],
)
def test_rupees_to_paise(raw, expected: int) -> None:
    assert rupees_to_paise(raw) == expected


def test_rupees_to_paise_rejects_negative() -> None:
    with pytest.raises(ValueError):
        rupees_to_paise("-1")


def test_rupees_to_paise_rejects_garbage() -> None:
    with pytest.raises(ValueError):
        rupees_to_paise("banana")


def test_paise_display_indian_grouping() -> None:
    assert paise_display(4_320_050) == "₹43,200.50"
    assert paise_display(0) == "₹0.00"
    assert paise_display(1_23_45_678_90) == "₹1,23,45,678.90"


def _invoice(**overrides):
    base = dict(
        gstin_profile_id="11111111-1111-1111-1111-111111111111",
        direction="purchase",
        invoice_number="INV-001",
        invoice_date=date(2026, 6, 15),
        counterparty_gstin="29ABCDE1234F1Z5",
        taxable_value_paise=100_000,
        cgst_paise=9_000,
        sgst_paise=9_000,
        igst_paise=0,
        total_paise=118_000,
    )
    base.update(overrides)
    return CanonicalInvoice(**base)


def test_content_hash_stable_across_number_variants() -> None:
    """The whole point of normalization: these three variants must dedup."""
    a = _invoice(invoice_number="INV-001")
    b = _invoice(invoice_number="inv 1")
    c = _invoice(invoice_number="0001")
    # 'inv 1' -> 'INV1'; '0001' -> '1'; 'INV-001' -> 'INV1'
    # So a and b collide, c does NOT (different logical number).
    assert a.content_hash() == b.content_hash()
    assert a.content_hash() != c.content_hash()


def test_content_hash_differs_by_total() -> None:
    a = _invoice(total_paise=118_000)
    b = _invoice(total_paise=118_100)
    assert a.content_hash() != b.content_hash()


def test_content_hash_differs_by_gstin_profile() -> None:
    a = _invoice(gstin_profile_id="11111111-1111-1111-1111-111111111111")
    b = _invoice(gstin_profile_id="22222222-2222-2222-2222-222222222222")
    assert a.content_hash() != b.content_hash()


def test_content_hash_case_insensitive_on_counterparty_gstin() -> None:
    a = _invoice(counterparty_gstin="29abcde1234f1z5")
    b = _invoice(counterparty_gstin="29ABCDE1234F1Z5")
    assert a.content_hash() == b.content_hash()
