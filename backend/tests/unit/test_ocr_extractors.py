"""Unit tests for text → invoice field regex heuristics.

Every extractor is pure (str in → FieldConfidence out), so these tests
run without a DB. Load-bearing properties:

* Labeled matches are high confidence (0.85+); unlabeled fallbacks
  are lower (0.65 or 0.3).
* GSTIN checksum passes → confidence=1.0; regex-only match → 0.5 (so
  the CA still sees the string and can correct it).
* Indian-format money (1,00,000.00) parses to paise correctly.
* Tax arithmetic warning fires when taxable+cgst+sgst+igst ≠ total.
"""
from __future__ import annotations

import pytest

from app.ocr.extractors import (
    extract_all_fields,
    extract_cgst_paise,
    extract_hsn_sac,
    extract_invoice_date,
    extract_invoice_number,
    extract_sgst_paise,
    extract_supplier_gstin,
    extract_taxable_value_paise,
    extract_total_paise,
    rollup_confidence,
    tax_arithmetic_warning,
)


# ---------------------------------------------------------------------------
# GSTIN
# ---------------------------------------------------------------------------


class TestGstinExtractor:
    def test_labeled_valid_gstin_returns_full_confidence(self) -> None:
        text = "Supplier GSTIN: 29ABCDE1234F1ZW\nOther text"
        out = extract_supplier_gstin(text)
        assert out.value == "29ABCDE1234F1ZW"
        assert out.confidence == 1.0

    def test_labeled_gstin_with_bad_checksum_gets_medium_confidence(self) -> None:
        # Structure OK, but checksum digit deliberately wrong (5 → 6).
        text = "GSTIN: 29ABCDE1234F1Z6"
        out = extract_supplier_gstin(text)
        assert out.value == "29ABCDE1234F1Z6"
        assert out.confidence == 0.5

    def test_unlabeled_valid_gstin_gets_medium_confidence(self) -> None:
        text = "Bill from 29ABCDE1234F1ZW for services"
        out = extract_supplier_gstin(text)
        assert out.value == "29ABCDE1234F1ZW"
        assert out.confidence == 0.65

    def test_no_gstin_returns_none(self) -> None:
        out = extract_supplier_gstin("Just prose here, no ID")
        assert out.value is None
        assert out.confidence == 0.0


# ---------------------------------------------------------------------------
# Invoice number
# ---------------------------------------------------------------------------


class TestInvoiceNumberExtractor:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Invoice No: INV-2026-0001", "INV-2026-0001"),
            ("Invoice Number: ACME/07/8912", "ACME/07/8912"),
            ("Bill No.: BILL_042", "BILL_042"),
            ("Doc # 2024-999", "2024-999"),
        ],
    )
    def test_labeled_matches(self, text: str, expected: str) -> None:
        out = extract_invoice_number(text)
        assert out.value == expected
        assert out.confidence == 0.85

    def test_no_label_returns_none(self) -> None:
        assert extract_invoice_number("Random prose, no invoice id").value is None


# ---------------------------------------------------------------------------
# Invoice date
# ---------------------------------------------------------------------------


class TestInvoiceDateExtractor:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Invoice Date: 2026-07-15", "2026-07-15"),
            ("Invoice Date: 15-07-2026", "2026-07-15"),
            ("Invoice Date: 15/07/2026", "2026-07-15"),
            ("Bill Date: 15 Jul 2026", "2026-07-15"),
            ("Date: 15.07.2026", "2026-07-15"),
        ],
    )
    def test_labeled_dates_parse_to_iso(self, text: str, expected: str) -> None:
        out = extract_invoice_date(text)
        assert out.value == expected
        assert out.confidence == 1.0

    def test_unlabeled_date_lower_confidence(self) -> None:
        text = "Payment made on 2026-07-15 for the services"
        out = extract_invoice_date(text)
        assert out.value == "2026-07-15"
        assert out.confidence == 0.65


# ---------------------------------------------------------------------------
# Money extractors
# ---------------------------------------------------------------------------


class TestMoneyExtractors:
    def test_taxable_value_indian_format(self) -> None:
        text = "Taxable Value:     1,00,000.00"
        out = extract_taxable_value_paise(text)
        assert out.value == "10000000"  # ₹1,00,000 → 10,000,000 paise
        assert out.confidence == 0.85

    def test_cgst_missing_defaults_to_zero_low_confidence(self) -> None:
        # Purely intra-state invoice with no CGST line — treat as ₹0
        # but surface low confidence so the CA can override.
        out = extract_cgst_paise("Taxable: 10000\nSGST: 900\nTotal: 10900")
        assert out.value == "0"
        assert out.confidence == 0.4

    def test_total_prefers_grand_total(self) -> None:
        text = "Total: 100.00\nGrand Total: 11,800.00"
        out = extract_total_paise(text)
        # Grand Total label is preferred → 11800 * 100 = 1180000 paise.
        assert out.value == "1180000"

    def test_rupee_symbol_and_currency_prefix_tolerated(self) -> None:
        assert extract_taxable_value_paise("Taxable Value: ₹1,000.00").value == "100000"
        assert extract_taxable_value_paise("Taxable Value: Rs. 1000").value == "100000"
        assert extract_taxable_value_paise("Taxable Value: INR 1000.50").value == "100050"


# ---------------------------------------------------------------------------
# HSN
# ---------------------------------------------------------------------------


class TestHsnExtractor:
    def test_labeled_match(self) -> None:
        out = extract_hsn_sac("HSN: 998311  Consulting services")
        assert out.value == "998311"
        assert out.confidence == 0.85

    def test_sac_label_accepted(self) -> None:
        assert extract_hsn_sac("SAC 9954").value == "9954"

    def test_no_label(self) -> None:
        assert extract_hsn_sac("Consulting: 10000").value is None


# ---------------------------------------------------------------------------
# Rollup + arithmetic warning
# ---------------------------------------------------------------------------


class TestRollupConfidence:
    def test_mean_of_found_fields(self) -> None:
        text = (
            "GSTIN: 29ABCDE1234F1ZW\n"
            "Invoice No: INV-1\n"
            "Invoice Date: 2026-07-15\n"
            "Taxable Value: 10,000.00\n"
            "CGST: 900.00\n"
            "SGST: 900.00\n"
            "Total (INR): 11,800.00\n"
            "HSN: 998311\n"
        )
        fields = extract_all_fields(text)
        rollup = rollup_confidence(fields)
        # Every field has a value; IGST defaults to 0 at low confidence
        # since no IGST line is present, which pulls the mean down
        # slightly. Anything ≥0.80 means the load-bearing fields all
        # matched.
        assert rollup >= 0.80

    def test_all_empty_rollup_is_zero(self) -> None:
        fields = extract_all_fields("just prose, nothing to find")
        # CGST/SGST/IGST have implicit-zero defaults, so their values are
        # not None — but their confidence is 0.4 each; if nothing else is
        # found, the rollup is the mean of those three ≈ 0.4.
        rollup = rollup_confidence(fields)
        assert 0.35 <= rollup <= 0.45


class TestTaxArithmeticWarning:
    def test_none_when_consistent(self) -> None:
        # 10000 + 900 + 900 + 0 = 11800 → matches total
        assert tax_arithmetic_warning(10000, 900, 900, 0, 11800) is None

    def test_warns_when_off_by_more_than_a_rupee(self) -> None:
        w = tax_arithmetic_warning(10000, 900, 900, 0, 12000)
        assert w is not None
        assert "mismatch" in w

    def test_tolerates_rounding(self) -> None:
        # 100 paise = ₹1 tolerance; 99 paise off is fine.
        assert tax_arithmetic_warning(10000, 900, 900, 0, 11799) is None

    def test_none_when_missing_input(self) -> None:
        assert tax_arithmetic_warning(None, 900, 900, 0, 11800) is None
