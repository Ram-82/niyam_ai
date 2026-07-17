"""Unit tests for the 8 P1 validation rules.

Each rule has its own section. Shared fixtures:

* ``ctx()`` — builds a ValidationContext against the seeded rule pack
  shape (we hand-construct the payload here so the tests don't need a DB).
* ``inv()`` — builds a CanonicalInvoice with sensible defaults.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.engines.validation import rules
from app.engines.validation.gstin import compute_check_digit
from app.engines.validation.pipeline import run_pipeline
from app.engines.validation.types import Flag, ValidationContext
from app.ingestion.canonical import CanonicalInvoice


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _valid_gstin(base: str = "29AAAAA0000A1Z") -> str:
    return base + compute_check_digit(base)


CLIENT_GSTIN = _valid_gstin("29AAAAA0000A1Z")       # Karnataka
SUPPLIER_KA = _valid_gstin("29BBBBB1234C2Z")        # Karnataka (intra-state with client)
SUPPLIER_MH = _valid_gstin("27CCCCC5678D3Z")        # Maharashtra (inter-state)


DEFAULT_PAYLOAD = {
    "validation": {
        "r004_hsn": {
            "default_severity": "warning",
            "default_min_digits": 4,
            "turnover_slabs": [
                {"max_turnover_crores": 5, "severity": "warning", "min_digits": 4},
                {"max_turnover_crores": None, "severity": "error", "min_digits": 6},
            ],
        },
        "r006_tax_arithmetic": {
            "expected_rate_percents": [0, 5, 12, 18, 28],
            "tolerance_paise": 100,
        },
        "r007_duplicate": {"enabled": True},
    }
}


def _ctx(**over) -> ValidationContext:
    base = dict(
        rule_pack_version="1.0.0",
        rule_pack_payload=DEFAULT_PAYLOAD,
        period="202606",
        today=date(2026, 7, 5),
        client_state_code="29",
        annual_turnover_paise=None,
        duplicate_key_counts={},
    )
    base.update(over)
    return ValidationContext(**base)


def _inv(**over) -> CanonicalInvoice:
    base = dict(
        gstin_profile_id="11111111-1111-1111-1111-111111111111",
        direction="purchase",
        invoice_number="INV-001",
        invoice_date=date(2026, 6, 15),
        counterparty_gstin=SUPPLIER_KA,
        taxable_value_paise=100_000,
        cgst_paise=9_000,
        sgst_paise=9_000,
        igst_paise=0,
        total_paise=118_000,
        hsn_sac="998311",
    )
    base.update(over)
    return CanonicalInvoice(**base)


# ---------------------------------------------------------------------------
# R001 GSTIN_MISSING
# ---------------------------------------------------------------------------


def test_r001_flags_purchase_without_counterparty() -> None:
    inv = _inv(counterparty_gstin=None)
    flag = rules.r001_gstin_missing(inv, _ctx())
    assert flag is not None and flag.rule_code == "R001" and flag.severity == "error"


def test_r001_passes_when_counterparty_present() -> None:
    assert rules.r001_gstin_missing(_inv(), _ctx()) is None


def test_r001_skips_sales_direction() -> None:
    """B2C sales without a counterparty GSTIN are not R001 errors."""
    inv = _inv(direction="sale", counterparty_gstin=None)
    assert rules.r001_gstin_missing(inv, _ctx()) is None


# ---------------------------------------------------------------------------
# R002 GSTIN_CHECKSUM
# ---------------------------------------------------------------------------


def test_r002_passes_for_valid_checksum() -> None:
    assert rules.r002_gstin_checksum(_inv(), _ctx()) is None


def test_r002_flags_bad_structure() -> None:
    inv = _inv(counterparty_gstin="not-a-gstin")
    f = rules.r002_gstin_checksum(inv, _ctx())
    assert f is not None
    assert "format" in f.message


def test_r002_flags_bad_checksum_but_valid_structure() -> None:
    # Bump the last char of a valid GSTIN to a different value.
    good = SUPPLIER_MH
    bad = good[:-1] + ("0" if good[-1] != "0" else "1")
    inv = _inv(counterparty_gstin=bad)
    f = rules.r002_gstin_checksum(inv, _ctx())
    assert f is not None
    assert "check digit" in f.message


def test_r002_skips_when_missing() -> None:
    """R001 owns the missing case; R002 does not double-flag."""
    inv = _inv(counterparty_gstin=None)
    assert rules.r002_gstin_checksum(inv, _ctx()) is None


# ---------------------------------------------------------------------------
# R003 DATE_OUT_OF_PERIOD
# ---------------------------------------------------------------------------


def test_r003_passes_when_in_period() -> None:
    inv = _inv(invoice_date=date(2026, 6, 30))
    assert rules.r003_date_out_of_period(inv, _ctx(period="202606")) is None


def test_r003_flags_previous_month() -> None:
    inv = _inv(invoice_date=date(2026, 5, 30))
    f = rules.r003_date_out_of_period(inv, _ctx(period="202606"))
    assert f is not None and f.severity == "warning"


def test_r003_flags_next_month() -> None:
    inv = _inv(invoice_date=date(2026, 7, 1))
    assert rules.r003_date_out_of_period(inv, _ctx(period="202606")) is not None


# ---------------------------------------------------------------------------
# R004 HSN_MISSING (turnover-slab aware)
# ---------------------------------------------------------------------------


def test_r004_passes_with_adequate_hsn() -> None:
    inv = _inv(hsn_sac="998311")  # 6 digits
    assert rules.r004_hsn_missing(inv, _ctx()) is None


def test_r004_flags_missing_hsn_default_warning() -> None:
    inv = _inv(hsn_sac=None)
    f = rules.r004_hsn_missing(inv, _ctx(annual_turnover_paise=None))
    assert f is not None
    assert f.severity == "warning"  # default when turnover unknown


def test_r004_flags_missing_hsn_high_turnover_error() -> None:
    # Turnover > 5 crores = catch-all slab (severity error).
    inv = _inv(hsn_sac=None)
    f = rules.r004_hsn_missing(
        inv, _ctx(annual_turnover_paise=10 * 10_000_000_00 + 1)  # >5 cr
    )
    assert f is not None
    assert f.severity == "error"


def test_r004_flags_too_few_digits_for_high_turnover() -> None:
    inv = _inv(hsn_sac="9983")  # 4 digits, but high turnover needs 6
    f = rules.r004_hsn_missing(
        inv, _ctx(annual_turnover_paise=10 * 10_000_000_00 + 1)
    )
    assert f is not None
    assert f.severity == "error"


def test_r004_low_turnover_accepts_4_digits() -> None:
    inv = _inv(hsn_sac="9983")
    # 3 crores -> slab 1 (min_digits 4, severity warning)
    assert rules.r004_hsn_missing(
        inv, _ctx(annual_turnover_paise=3 * 10_000_000_00)
    ) is None


# ---------------------------------------------------------------------------
# R005 TAX_HEAD_MISMATCH
# ---------------------------------------------------------------------------


def test_r005_passes_intra_state_cgst_sgst() -> None:
    inv = _inv(
        counterparty_gstin=SUPPLIER_KA,  # 29 == client state 29
        cgst_paise=9_000, sgst_paise=9_000, igst_paise=0,
    )
    assert rules.r005_tax_head_mismatch(inv, _ctx()) is None


def test_r005_flags_intra_state_with_igst() -> None:
    inv = _inv(
        counterparty_gstin=SUPPLIER_KA,
        cgst_paise=0, sgst_paise=0, igst_paise=18_000,
    )
    f = rules.r005_tax_head_mismatch(inv, _ctx())
    assert f is not None and f.severity == "error"


def test_r005_passes_inter_state_igst_only() -> None:
    inv = _inv(
        counterparty_gstin=SUPPLIER_MH,  # 27 vs client 29
        cgst_paise=0, sgst_paise=0, igst_paise=18_000,
    )
    assert rules.r005_tax_head_mismatch(inv, _ctx()) is None


def test_r005_flags_inter_state_with_cgst_sgst() -> None:
    inv = _inv(
        counterparty_gstin=SUPPLIER_MH,
        cgst_paise=9_000, sgst_paise=9_000, igst_paise=0,
    )
    f = rules.r005_tax_head_mismatch(inv, _ctx())
    assert f is not None


def test_r005_skips_missing_counterparty() -> None:
    inv = _inv(counterparty_gstin=None)
    assert rules.r005_tax_head_mismatch(inv, _ctx()) is None


# ---------------------------------------------------------------------------
# R006 TAX_ARITHMETIC
# ---------------------------------------------------------------------------


def test_r006_passes_18_percent_split_evenly() -> None:
    # taxable 1000 * 18% = 180 total; split 90/90
    inv = _inv(
        taxable_value_paise=100_000, cgst_paise=9_000,
        sgst_paise=9_000, igst_paise=0, total_paise=118_000,
    )
    assert rules.r006_tax_arithmetic(inv, _ctx()) is None


def test_r006_passes_18_percent_as_igst() -> None:
    inv = _inv(
        taxable_value_paise=100_000, cgst_paise=0,
        sgst_paise=0, igst_paise=18_000, total_paise=118_000,
    )
    assert rules.r006_tax_arithmetic(inv, _ctx()) is None


def test_r006_flags_wrong_arithmetic() -> None:
    # 1000 * 18% should be 180 total; put 200 instead
    inv = _inv(
        taxable_value_paise=100_000, cgst_paise=10_000,
        sgst_paise=10_000, igst_paise=0, total_paise=120_000,
    )
    f = rules.r006_tax_arithmetic(inv, _ctx())
    assert f is not None and f.severity == "error"


def test_r006_passes_within_tolerance() -> None:
    # 1000 * 18% = 180.00 = 18000 paise. Off by 50 paise → within 100 tolerance.
    inv = _inv(
        taxable_value_paise=100_000, cgst_paise=9_025,
        sgst_paise=9_025, igst_paise=0, total_paise=118_050,
    )
    assert rules.r006_tax_arithmetic(inv, _ctx()) is None


def test_r006_passes_zero_value_line() -> None:
    inv = _inv(
        taxable_value_paise=0, cgst_paise=0,
        sgst_paise=0, igst_paise=0, total_paise=0,
    )
    assert rules.r006_tax_arithmetic(inv, _ctx()) is None


def test_r006_passes_zero_rated() -> None:
    inv = _inv(
        taxable_value_paise=100_000, cgst_paise=0,
        sgst_paise=0, igst_paise=0, total_paise=100_000,
    )
    assert rules.r006_tax_arithmetic(inv, _ctx()) is None


# ---------------------------------------------------------------------------
# R007 DUPLICATE_SUSPECT
# ---------------------------------------------------------------------------


def test_r007_flags_when_count_gt_1() -> None:
    inv = _inv(invoice_number="INV-001")
    from app.ingestion.canonical import normalize_invoice_number
    key = (inv.counterparty_gstin.upper(), normalize_invoice_number("INV-001"))
    ctx = _ctx(duplicate_key_counts={key: 2})
    f = rules.r007_duplicate_suspect(inv, ctx)
    assert f is not None and f.severity == "warning"
    assert "2 invoices share" in f.message


def test_r007_passes_when_count_is_1() -> None:
    inv = _inv(invoice_number="INV-001")
    from app.ingestion.canonical import normalize_invoice_number
    key = (inv.counterparty_gstin.upper(), normalize_invoice_number("INV-001"))
    ctx = _ctx(duplicate_key_counts={key: 1})
    assert rules.r007_duplicate_suspect(inv, ctx) is None


def test_r007_skips_missing_counterparty() -> None:
    inv = _inv(counterparty_gstin=None)
    assert rules.r007_duplicate_suspect(inv, _ctx()) is None


def test_r007_respects_disable_flag() -> None:
    payload = {
        "validation": {"r007_duplicate": {"enabled": False}}
    }
    ctx = _ctx(rule_pack_payload=payload, duplicate_key_counts={
        (SUPPLIER_KA, "INV1"): 5
    })
    assert rules.r007_duplicate_suspect(_inv(), ctx) is None


# ---------------------------------------------------------------------------
# R008 FUTURE_DATE
# ---------------------------------------------------------------------------


def test_r008_passes_for_past_date() -> None:
    inv = _inv(invoice_date=date(2026, 6, 15))
    ctx = _ctx(today=date(2026, 7, 5))
    assert rules.r008_future_date(inv, ctx) is None


def test_r008_passes_for_today() -> None:
    d = date(2026, 7, 5)
    inv = _inv(invoice_date=d)
    ctx = _ctx(today=d)
    assert rules.r008_future_date(inv, ctx) is None


def test_r008_flags_future_date() -> None:
    inv = _inv(invoice_date=date(2027, 1, 1))
    ctx = _ctx(today=date(2026, 7, 5))
    f = rules.r008_future_date(inv, ctx)
    assert f is not None and f.severity == "error"


# ---------------------------------------------------------------------------
# Pipeline integration — a single invoice tripping multiple rules at once
# ---------------------------------------------------------------------------


def test_pipeline_returns_multiple_flags() -> None:
    """A messy invoice: missing GSTIN (R001), missing HSN (R004),
    wrong arithmetic (R006), and future-dated (R008)."""
    inv = _inv(
        counterparty_gstin=None,
        hsn_sac=None,
        taxable_value_paise=100_000,
        cgst_paise=100, sgst_paise=100, igst_paise=0, total_paise=100_200,
        invoice_date=date(2030, 1, 1),
    )
    ctx = _ctx(today=date(2026, 7, 5))
    flags = run_pipeline(inv, ctx)
    codes = {f.rule_code for f in flags}
    assert {"R001", "R004", "R006", "R008"}.issubset(codes)
    # R002 is skipped when GSTIN is missing (R001 owns that case).
    assert "R002" not in codes


def test_pipeline_empty_on_clean_invoice() -> None:
    inv = _inv()  # clean defaults
    flags = run_pipeline(inv, _ctx())
    assert flags == []
