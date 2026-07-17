"""Unit tests for the pure scoring calculator.

Everything here operates on ``ScoreInputs`` — no DB, no rule pack lookup,
no wall-clock. If the DB-side changes, this file shouldn't need to.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.engines.scoring.calculator import compute_score
from app.engines.scoring.types import Blocker, ScoreInputs


DEFAULT_WEIGHTS = {
    "validation_pass_rate": 25,
    "reconciliation_match_rate": 40,
    "data_completeness": 15,
    "supplier_risk": 10,
    "days_to_due_date": 10,
}


def _inputs(**over) -> ScoreInputs:
    """Build inputs for a clean, filing-ready return by default. Tests
    override specific fields to exercise each component."""
    base = dict(
        rule_pack_version="1.0.0",
        weights=DEFAULT_WEIGHTS,
        days_to_due_date_curve_days=14,
        return_type="GSTR1",
        period="202606",
        today=date(2026, 7, 5),
        invoice_count=10,
        validation_error_count=0,
        validation_warning_count=0,
        recon_summary={
            "matched": {"count": 10, "paise": 1_000_000, "description": "..."},
            "probable": {"count": 0, "paise": 0, "description": "..."},
            "supplier_default": {
                "count": 0, "paise": 0, "top_suppliers": [], "with_near_misses": 0,
                "description": "...",
            },
            "missing_entry": {"count": 0, "paise": 0, "description": "..."},
            "disclaimer": "before credit/debit note adjustments",
        },
        total_register_paise=1_000_000,
        trailing_month_counts=[9, 10, 11],
        current_month_count=10,
        risky_supplier_paise=0,
        total_supplier_paise=1_000_000,
        days_to_due_date=6,
        error_invoice_paise=0,
        warning_invoice_paise=0,
    )
    base.update(over)
    return ScoreInputs(**base)


# ---------------------------------------------------------------------------
# Component behaviour
# ---------------------------------------------------------------------------


def test_clean_return_scores_high() -> None:
    result = compute_score(_inputs())
    # 100 val, 100 recon, 100 completeness, 100 supplier_risk,
    # 6/14 ≈ 43 days score → weighted avg on the default weights:
    # 25*100 + 40*100 + 15*100 + 10*100 + 10*42.86 = 2500 + 4000 + 1500 + 1000 + 428.6 = 9428.6 / 100 = 94.29
    assert 93 <= result.score <= 95
    assert result.arithmetic["rule_pack_version"] == "1.0.0"


def test_validation_errors_hurt_more_than_warnings() -> None:
    # 5 errors on 10 invoices vs 5 warnings on 10 invoices.
    r_err = compute_score(_inputs(validation_error_count=5))
    r_warn = compute_score(_inputs(validation_warning_count=5))
    assert r_err.score < r_warn.score


def test_reconciliation_match_rate_is_value_based_not_count() -> None:
    """Match rate uses paise, not count. 1 matched invoice for ₹90 out of
    ₹100 total → 90%, not 1/1 → 100%."""
    inp = _inputs(
        recon_summary={
            "matched": {"count": 1, "paise": 90_000},
            "probable": {"count": 0, "paise": 0},
            "supplier_default": {"count": 1, "paise": 10_000, "top_suppliers": []},
            "missing_entry": {"count": 0, "paise": 0},
        },
        total_register_paise=100_000,
        risky_supplier_paise=0,
        total_supplier_paise=100_000,
    )
    result = compute_score(inp)
    recon = next(c for c in result.components if c.name == "reconciliation_match_rate")
    assert recon.value == 90.0


def test_data_completeness_uses_trailing_average() -> None:
    """Current 5 vs trailing avg 10 → 50% completeness."""
    inp = _inputs(
        current_month_count=5,
        trailing_month_counts=[10, 10, 10],
        invoice_count=5,
    )
    result = compute_score(inp)
    comp = next(c for c in result.components if c.name == "data_completeness")
    assert comp.value == 50.0


def test_supplier_risk_penalizes_when_risky_paise_high() -> None:
    inp = _inputs(
        risky_supplier_paise=800_000,
        total_supplier_paise=1_000_000,
    )
    result = compute_score(inp)
    sr = next(c for c in result.components if c.name == "supplier_risk")
    assert sr.value == 20.0  # 100 * (1 - 0.8) = 20


def test_days_to_due_date_curve() -> None:
    # 0 days == 0 score. 14 days == 100 score.
    r0 = compute_score(_inputs(days_to_due_date=0))
    r14 = compute_score(_inputs(days_to_due_date=14))
    c0 = next(c for c in r0.components if c.name == "days_to_due_date")
    c14 = next(c for c in r14.components if c.name == "days_to_due_date")
    assert c0.value == 0.0
    assert c14.value == 100.0


def test_overdue_scores_zero_on_time_component() -> None:
    r_overdue = compute_score(_inputs(days_to_due_date=-2))
    c = next(x for x in r_overdue.components if x.name == "days_to_due_date")
    assert c.value == 0.0


def test_score_is_integer_zero_to_hundred() -> None:
    r_low = compute_score(_inputs(
        validation_error_count=10,
        recon_summary={
            "matched": {"count": 0, "paise": 0},
            "probable": {"count": 0, "paise": 0},
            "supplier_default": {"count": 10, "paise": 1_000_000, "top_suppliers": []},
            "missing_entry": {"count": 0, "paise": 0},
        },
        total_register_paise=1_000_000,
        risky_supplier_paise=1_000_000,
        total_supplier_paise=1_000_000,
        current_month_count=0,
        trailing_month_counts=[10, 10, 10],
        days_to_due_date=0,
    ))
    assert 0 <= r_low.score <= 5
    assert isinstance(r_low.score, int)


# ---------------------------------------------------------------------------
# Weight normalization — adding a new component shouldn't destabilize
# ---------------------------------------------------------------------------


def test_zero_total_weight_still_returns_a_score() -> None:
    """Broken rule pack: all weights zero. Should return 0 rather than crash."""
    result = compute_score(_inputs(weights={k: 0 for k in DEFAULT_WEIGHTS}))
    assert result.score == 0


def test_missing_weight_treated_as_zero() -> None:
    """Rule pack omits days_to_due_date weight: rest still work."""
    weights = dict(DEFAULT_WEIGHTS)
    del weights["days_to_due_date"]
    result = compute_score(_inputs(weights=weights))
    # Clean baseline → 100 on the other four → score ~100
    assert result.score >= 99


# ---------------------------------------------------------------------------
# Arithmetic breakdown — the "click to see math" data
# ---------------------------------------------------------------------------


def test_arithmetic_shows_full_breakdown() -> None:
    result = compute_score(_inputs())
    ar = result.arithmetic
    assert set(c["name"] for c in ar["components"]) == set(DEFAULT_WEIGHTS.keys())
    for c in ar["components"]:
        assert "value" in c
        assert "raw_weight" in c
        assert "normalized_weight" in c
        assert "weighted_contribution" in c
    assert ar["final_score"] == result.score
    assert abs(ar["weighted_sum"] - result.score) < 1.0  # rounding


# ---------------------------------------------------------------------------
# Blockers — paise_impact comes from recon summary
# ---------------------------------------------------------------------------


def test_supplier_default_blocker_paise_impact_from_recon() -> None:
    inp = _inputs(
        recon_summary={
            "matched": {"count": 5, "paise": 500_000},
            "probable": {"count": 0, "paise": 0},
            "supplier_default": {
                "count": 6,
                "paise": 43_000_00,  # ₹43,000 in paise (43000 * 100)
                "top_suppliers": [
                    {"supplier_gstin": "29X", "paise": 25_000_00, "count": 3},
                    {"supplier_gstin": "27Y", "paise": 18_000_00, "count": 3},
                ],
            },
            "missing_entry": {"count": 0, "paise": 0},
        },
        total_register_paise=1_000_000,
    )
    result = compute_score(inp)
    codes = {b.code: b for b in result.blockers}

    assert "SUPPLIER_DEFAULT_TOTAL" in codes
    assert codes["SUPPLIER_DEFAULT_TOTAL"].paise_impact == 43_000_00

    # Per-supplier blockers spawned from top_suppliers.
    assert "TOP_DEFAULT_SUPPLIER_29X" in codes
    assert codes["TOP_DEFAULT_SUPPLIER_29X"].paise_impact == 25_000_00
    assert codes["TOP_DEFAULT_SUPPLIER_27Y"].paise_impact == 18_000_00


def test_probable_blocker_paise_impact_from_recon() -> None:
    inp = _inputs(
        recon_summary={
            "matched": {"count": 0, "paise": 0},
            "probable": {"count": 3, "paise": 150_000},
            "supplier_default": {"count": 0, "paise": 0, "top_suppliers": []},
            "missing_entry": {"count": 0, "paise": 0},
        },
    )
    result = compute_score(inp)
    codes = {b.code: b for b in result.blockers}
    assert codes["PROBABLE_PENDING_REVIEW"].paise_impact == 150_000
    assert codes["PROBABLE_PENDING_REVIEW"].owner == "ca"


def test_missing_entry_blocker_is_client_owned() -> None:
    inp = _inputs(
        recon_summary={
            "matched": {"count": 0, "paise": 0},
            "probable": {"count": 0, "paise": 0},
            "supplier_default": {"count": 0, "paise": 0, "top_suppliers": []},
            "missing_entry": {"count": 2, "paise": 12_000},
        },
    )
    result = compute_score(inp)
    codes = {b.code: b for b in result.blockers}
    assert codes["MISSING_ENTRY_TOTAL"].owner == "client"
    assert codes["MISSING_ENTRY_TOTAL"].paise_impact == 12_000


def test_validation_blockers_carry_impacted_invoice_paise() -> None:
    inp = _inputs(
        validation_error_count=3,
        validation_warning_count=5,
        error_invoice_paise=45_000,
        warning_invoice_paise=22_500,
    )
    result = compute_score(inp)
    codes = {b.code: b for b in result.blockers}
    assert codes["VALIDATION_ERRORS"].paise_impact == 45_000
    assert codes["VALIDATION_WARNINGS"].paise_impact == 22_500


def test_deadline_blocker_appears_at_short_horizon() -> None:
    r_close = compute_score(_inputs(days_to_due_date=2))
    r_far = compute_score(_inputs(days_to_due_date=10))
    close_codes = {b.code for b in r_close.blockers}
    far_codes = {b.code for b in r_far.blockers}
    assert "DEADLINE_IMMINENT" in close_codes
    assert "DEADLINE_IMMINENT" not in far_codes


def test_blockers_sorted_by_paise_impact_desc() -> None:
    inp = _inputs(
        validation_error_count=2,
        error_invoice_paise=10_000,
        recon_summary={
            "matched": {"count": 0, "paise": 0},
            "probable": {"count": 1, "paise": 5_000},
            "supplier_default": {
                "count": 3, "paise": 100_000,
                "top_suppliers": [{"supplier_gstin": "29X", "paise": 60_000, "count": 2}],
            },
            "missing_entry": {"count": 1, "paise": 1_000},
        },
    )
    result = compute_score(inp)
    impacts = [b.paise_impact for b in result.blockers]
    assert impacts == sorted(impacts, reverse=True)
