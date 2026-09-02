"""Reconciliation algorithm tests.

The prompt calls out four edge cases explicitly, so each has a dedicated
test:

1. Invoice number written as ``INV-001`` vs ``inv 1`` vs ``0001``.
2. Same supplier multiple invoices same amount (no double-matching).
3. Rounding differences at the exact/fuzzy boundary.
4. Multiple 2B entries competing for one register invoice.

Plus the buckets themselves: matched, probable, supplier_default,
missing_entry. Plus determinism across runs (same inputs → same output).
"""
from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest

from app.engines.reconciliation.passes import reconcile
from app.engines.reconciliation.scoring import score_pair
from app.engines.reconciliation.types import (
    B2BLine,
    MatchPair,
    ReconConfig,
    RegisterLine,
    Residual,
)
from app.ingestion.canonical import normalize_invoice_number


CFG = ReconConfig(
    exact_amount_tolerance_paise=100,
    date_window_days=5,
    amount_tolerance_percent=1.0,
    probable_confidence_threshold=0.70,
    fuzzy_score_weights={
        "number_similarity": 0.5,
        "date_closeness": 0.25,
        "amount_closeness": 0.25,
    },
)


SUP_A = "29AAAAA0000A1ZY"  # supplier A (real check-digit not required in tests)
SUP_B = "27BBBBB1234C2Z8"


def _reg(
    *,
    number: str,
    date_: date,
    total: int,
    supplier: str = SUP_A,
    id_: UUID | None = None,
) -> RegisterLine:
    return RegisterLine(
        invoice_id=id_ or uuid4(),
        supplier_gstin=supplier,
        invoice_number=number,
        normalized_number=normalize_invoice_number(number),
        invoice_date=date_,
        total_paise=total,
    )


def _b2b(
    *,
    number: str,
    date_: date,
    total: int,
    supplier: str = SUP_A,
    id_: UUID | None = None,
) -> B2BLine:
    return B2BLine(
        b2b_entry_id=id_ or uuid4(),
        supplier_gstin=supplier,
        invoice_number=number,
        normalized_number=normalize_invoice_number(number),
        invoice_date=date_,
        total_paise=total,
        itc_available=True,
    )


# ---------------------------------------------------------------------------
# Exact matching
# ---------------------------------------------------------------------------


def test_exact_perfect_match() -> None:
    r = _reg(number="INV-1", date_=date(2026, 6, 15), total=118_000)
    b = _b2b(number="INV-1", date_=date(2026, 6, 15), total=118_000)
    result = reconcile([r], [b], CFG)
    assert len(result.pairs) == 1
    assert result.pairs[0].bucket == "matched"
    assert result.pairs[0].confidence == 1.0
    assert result.residuals == []


def test_exact_matches_normalized_number_variants() -> None:
    """The invoice-number-variants case from the prompt.

    "INV-001" and "inv 1" both normalize to "INV1" and must exact-match.
    "0001" normalizes to "1" which does NOT collide with "INV1".
    """
    r_inv001 = _reg(number="INV-001", date_=date(2026, 6, 15), total=118_000)
    r_inv1 = _reg(number="inv 1", date_=date(2026, 6, 15), total=118_000)
    r_0001 = _reg(number="0001", date_=date(2026, 6, 15), total=118_000)

    b_matches_first = _b2b(
        number="INV1", date_=date(2026, 6, 15), total=118_000
    )

    result = reconcile([r_inv001, r_inv1, r_0001], [b_matches_first], CFG)
    # One of INV-001/inv 1 matches; the other and 0001 fall to supplier_default.
    matched = [p for p in result.pairs if p.bucket == "matched"]
    assert len(matched) == 1
    matched_reg_id = matched[0].invoice_id
    assert matched_reg_id in (r_inv001.invoice_id, r_inv1.invoice_id)

    residual_ids = {r.invoice_id for r in result.residuals if r.bucket == "supplier_default"}
    # The other one AND the truly-different "0001" both fall to residual.
    assert r_0001.invoice_id in residual_ids
    assert len(residual_ids) == 2


def test_exact_tolerates_100_paise() -> None:
    r = _reg(number="INV-1", date_=date(2026, 6, 15), total=118_000)
    b = _b2b(number="INV-1", date_=date(2026, 6, 15), total=118_100)  # +₹1
    result = reconcile([r], [b], CFG)
    assert result.pairs[0].bucket == "matched"


def test_exact_rejects_beyond_tolerance() -> None:
    r = _reg(number="INV-1", date_=date(2026, 6, 15), total=118_000)
    b = _b2b(number="INV-1", date_=date(2026, 6, 15), total=118_500)  # +₹5
    result = reconcile([r], [b], CFG)
    # Falls through to fuzzy — same normalized number + same date → high
    # score, above threshold → probable.
    assert len(result.pairs) == 1
    assert result.pairs[0].bucket == "probable"


# ---------------------------------------------------------------------------
# Fuzzy matching
# ---------------------------------------------------------------------------


def test_fuzzy_within_date_window_produces_probable() -> None:
    r = _reg(number="INV-100", date_=date(2026, 6, 15), total=100_000)
    b = _b2b(number="INV/100", date_=date(2026, 6, 18), total=100_500)
    result = reconcile([r], [b], CFG)
    assert len(result.pairs) == 1
    assert result.pairs[0].bucket == "probable"
    assert 0.7 <= result.pairs[0].confidence < 1.0


def test_fuzzy_outside_date_window_is_residual() -> None:
    r = _reg(number="INV-100", date_=date(2026, 6, 15), total=100_000)
    b = _b2b(number="INV-100", date_=date(2026, 6, 30), total=100_000)  # +15 days
    result = reconcile([r], [b], CFG)
    assert result.pairs == []
    buckets = {res.bucket for res in result.residuals}
    assert buckets == {"supplier_default", "missing_entry"}


def test_fuzzy_different_supplier_never_matches() -> None:
    r = _reg(
        number="INV-1", date_=date(2026, 6, 15), total=100_000, supplier=SUP_A
    )
    b = _b2b(
        number="INV-1", date_=date(2026, 6, 15), total=100_000, supplier=SUP_B
    )
    result = reconcile([r], [b], CFG)
    assert result.pairs == []


# ---------------------------------------------------------------------------
# Greedy 1:1 assignment: prompt-required edge cases
# ---------------------------------------------------------------------------


def test_same_key_different_amounts_pair_by_closest() -> None:
    """The prompt-required test: two register invoices with same
    (supplier, normalized number, date) but different amounts, and two
    2B entries likewise. Correct pairing is by amount (₹1000↔₹1000,
    ₹1050↔₹1050), NOT by insertion order.

    A first-in-wins Pass 1 would cross-pair when the b2b insertion order
    differed from the register order.
    """
    # Deliberately construct so the "insertion order" pairing would be wrong:
    # register order [r_low, r_high], b2b order [b_high, b_low].
    r_low = _reg(
        number="DUP-1", date_=date(2026, 6, 15), total=100_000,
        id_=UUID("00000000-0000-0000-0000-000000000001"),
    )
    r_high = _reg(
        number="DUP-1", date_=date(2026, 6, 15), total=105_000,
        id_=UUID("00000000-0000-0000-0000-000000000002"),
    )
    b_high = _b2b(
        number="DUP-1", date_=date(2026, 6, 15), total=105_000,
        id_=UUID("00000000-0000-0000-0000-000000000003"),
    )
    b_low = _b2b(
        number="DUP-1", date_=date(2026, 6, 15), total=100_000,
        id_=UUID("00000000-0000-0000-0000-000000000004"),
    )

    result = reconcile([r_low, r_high], [b_high, b_low], CFG)

    # Both must exact-match (bucket=matched) and by amount, not by order.
    matched = {(p.invoice_id, p.b2b_entry_id) for p in result.pairs if p.bucket == "matched"}
    assert matched == {
        (r_low.invoice_id, b_low.b2b_entry_id),
        (r_high.invoice_id, b_high.b2b_entry_id),
    }
    assert result.residuals == []


def test_same_supplier_multiple_invoices_same_amount_no_double_match() -> None:
    """Two register invoices, two 2B entries, all same amount. Each side
    must pair 1:1 — no register invoice ends up matched to two 2B
    entries and vice versa."""
    r1 = _reg(number="INV-1", date_=date(2026, 6, 15), total=100_000)
    r2 = _reg(number="INV-2", date_=date(2026, 6, 20), total=100_000)
    b1 = _b2b(number="INV-1", date_=date(2026, 6, 15), total=100_000)
    b2 = _b2b(number="INV-2", date_=date(2026, 6, 20), total=100_000)

    result = reconcile([r1, r2], [b1, b2], CFG)
    assert len(result.pairs) == 2
    reg_ids = [p.invoice_id for p in result.pairs]
    b2b_ids = [p.b2b_entry_id for p in result.pairs]
    assert len(set(reg_ids)) == 2
    assert len(set(b2b_ids)) == 2


def test_multiple_2b_entries_competing_for_one_register_invoice() -> None:
    """Best-scoring 2B entry wins. The runner-up falls to missing_entry."""
    r = _reg(number="INV-1", date_=date(2026, 6, 15), total=100_000)
    b_best = _b2b(number="INV-1", date_=date(2026, 6, 15), total=100_000)
    b_worse = _b2b(number="INV-1", date_=date(2026, 6, 15), total=100_500)  # off by ₹5

    result = reconcile([r], [b_best, b_worse], CFG)
    matched = [p for p in result.pairs if p.bucket == "matched"]
    assert len(matched) == 1
    assert matched[0].b2b_entry_id == b_best.b2b_entry_id

    missing = [r_ for r_ in result.residuals if r_.bucket == "missing_entry"]
    assert len(missing) == 1
    assert missing[0].b2b_entry_id == b_worse.b2b_entry_id


# ---------------------------------------------------------------------------
# Residuals — the "found money" story
# ---------------------------------------------------------------------------


def test_register_only_becomes_supplier_default() -> None:
    r = _reg(number="INV-1", date_=date(2026, 6, 15), total=118_000)
    result = reconcile([r], [], CFG)
    assert result.pairs == []
    assert len(result.residuals) == 1
    assert result.residuals[0].bucket == "supplier_default"
    assert result.residuals[0].total_paise == 118_000
    assert result.residuals[0].supplier_gstin == SUP_A
    # No 2B entries at all -> nothing to surface as a near-miss.
    assert result.residuals[0].near_misses == ()


def test_supplier_default_surfaces_same_supplier_near_miss() -> None:
    """Register: INV-100. 2B has INV-999 from same supplier — outside
    the fuzzy amount tolerance so it doesn't match, but the number
    similarity is high enough that the CA should see it before deciding
    to chase the supplier."""
    r = _reg(
        number="INV-100", date_=date(2026, 6, 15), total=100_000, supplier=SUP_A,
    )
    # Huge amount diff (200%) so fuzzy Pass 2 disqualifies. Same normalized
    # number → near-miss discovery picks it up.
    b_similar = _b2b(
        number="INV-100", date_=date(2026, 6, 15), total=300_000, supplier=SUP_A,
    )
    # Different supplier → not a near-miss, must be excluded.
    b_other = _b2b(
        number="INV-100", date_=date(2026, 6, 15), total=100_000, supplier=SUP_B,
    )
    result = reconcile([r], [b_similar, b_other], CFG)

    sup_default = [r_ for r_ in result.residuals if r_.bucket == "supplier_default"]
    assert len(sup_default) == 1
    near = sup_default[0].near_misses
    assert len(near) == 1
    assert near[0].b2b_entry_id == b_similar.b2b_entry_id
    assert near[0].supplier_gstin == SUP_A
    assert near[0].similarity == 1.0  # exact normalized-number match


def test_near_miss_excluded_when_paired_in_pass_2() -> None:
    """A same-supplier b2b that DOES successfully match in Pass 2 must
    NOT appear as a near-miss on any subsequent supplier_default row."""
    r_paired = _reg(
        number="INV-1", date_=date(2026, 6, 15), total=100_000, supplier=SUP_A,
    )
    r_orphan = _reg(
        number="INV-2", date_=date(2026, 6, 15), total=50_000, supplier=SUP_A,
    )
    # This b2b probable-matches r_paired (Pass 2), so it's consumed.
    b_matches_r1 = _b2b(
        number="INV/1", date_=date(2026, 6, 16), total=100_100, supplier=SUP_A,
    )
    result = reconcile([r_paired, r_orphan], [b_matches_r1], CFG)

    sup_default = [r_ for r_ in result.residuals if r_.bucket == "supplier_default"]
    assert len(sup_default) == 1
    # r_orphan had no partner -> supplier_default; b_matches_r1 was consumed,
    # so it's NOT in near_misses.
    assert sup_default[0].near_misses == ()


def test_summary_reports_supplier_default_with_near_miss_count() -> None:
    r = _reg(number="INV-A", date_=date(2026, 6, 15), total=50_000, supplier=SUP_A)
    b_near = _b2b(number="INV-A", date_=date(2026, 6, 15), total=999_999, supplier=SUP_A)
    result = reconcile([r], [b_near], CFG)
    s = result.summary()
    assert s["supplier_default"]["with_near_misses"] == 1
    assert "review near_misses" in s["supplier_default"]["description"].lower()


def test_2b_only_becomes_missing_entry() -> None:
    b = _b2b(number="INV-1", date_=date(2026, 6, 15), total=118_000)
    result = reconcile([], [b], CFG)
    assert len(result.residuals) == 1
    assert result.residuals[0].bucket == "missing_entry"


# ---------------------------------------------------------------------------
# Summary — the "₹43,000 ITC at risk from 6 suppliers" story
# ---------------------------------------------------------------------------


def test_summary_paise_totals_and_top_suppliers() -> None:
    # 1 matched (100k), 1 probable (50k), 2 supplier_default (30k + 15k from same supplier;
    # 20k from another), 1 missing_entry (10k).
    r_matched = _reg(number="M-1", date_=date(2026, 6, 15), total=100_000)
    b_matched = _b2b(number="M-1", date_=date(2026, 6, 15), total=100_000)

    # Same normalized number (P-1 and P/1 both -> "P1") but different date
    # and slightly different amount — a classic "supplier typo" probable match.
    r_probable = _reg(number="P-1", date_=date(2026, 6, 15), total=50_000)
    b_probable = _b2b(number="P/1", date_=date(2026, 6, 17), total=50_100)

    r_def_a1 = _reg(number="D-1", date_=date(2026, 6, 10), total=30_000, supplier=SUP_A)
    r_def_a2 = _reg(number="D-2", date_=date(2026, 6, 11), total=15_000, supplier=SUP_A)
    r_def_b = _reg(number="D-3", date_=date(2026, 6, 12), total=20_000, supplier=SUP_B)

    b_missing = _b2b(number="X-1", date_=date(2026, 6, 15), total=10_000)

    result = reconcile(
        [r_matched, r_probable, r_def_a1, r_def_a2, r_def_b],
        [b_matched, b_probable, b_missing],
        CFG,
    )
    summary = result.summary()

    # Check counts + paise; the summary also carries copy fields
    # (description, with_near_misses) that don't belong in this test.
    assert summary["matched"]["count"] == 1
    assert summary["matched"]["paise"] == 100_000
    assert summary["probable"]["count"] == 1
    assert summary["probable"]["paise"] == 50_000
    assert summary["supplier_default"]["count"] == 3
    assert summary["supplier_default"]["paise"] == 30_000 + 15_000 + 20_000
    assert summary["missing_entry"]["count"] == 1
    assert summary["missing_entry"]["paise"] == 10_000
    assert "before credit/debit note adjustments" in summary["disclaimer"]

    # SUP_A owes 45k, SUP_B owes 20k. Ranked descending.
    top = summary["supplier_default"]["top_suppliers"]
    assert top[0]["supplier_gstin"] == SUP_A
    assert top[0]["paise"] == 45_000
    assert top[0]["count"] == 2
    assert top[1]["supplier_gstin"] == SUP_B


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_inputs_same_output() -> None:
    """Two runs with identical inputs must produce identical pair sets."""
    r1 = _reg(number="INV-1", date_=date(2026, 6, 15), total=100_000)
    r2 = _reg(number="INV-2", date_=date(2026, 6, 20), total=200_000)
    b1 = _b2b(number="INV-1", date_=date(2026, 6, 15), total=100_000)
    b2 = _b2b(number="INV-2", date_=date(2026, 6, 20), total=200_000)

    first = reconcile([r1, r2], [b1, b2], CFG)
    second = reconcile([r1, r2], [b1, b2], CFG)
    assert {p.invoice_id for p in first.pairs} == {p.invoice_id for p in second.pairs}


# ---------------------------------------------------------------------------
# Scoring — hard gates
# ---------------------------------------------------------------------------


def test_score_zero_for_different_supplier() -> None:
    r = _reg(number="INV-1", date_=date(2026, 6, 15), total=100_000, supplier=SUP_A)
    b = _b2b(number="INV-1", date_=date(2026, 6, 15), total=100_000, supplier=SUP_B)
    assert score_pair(r, b, CFG) == 0.0


def test_score_zero_outside_date_window() -> None:
    r = _reg(number="INV-1", date_=date(2026, 6, 15), total=100_000)
    b = _b2b(number="INV-1", date_=date(2026, 6, 25), total=100_000)
    assert score_pair(r, b, CFG) == 0.0


def test_score_zero_outside_amount_tolerance() -> None:
    r = _reg(number="INV-1", date_=date(2026, 6, 15), total=100_000)
    # 1% tolerance = 1000 paise. 100000 vs 105000 = 5000 diff → out.
    b = _b2b(number="INV-1", date_=date(2026, 6, 15), total=105_000)
    assert score_pair(r, b, CFG) == 0.0


def test_score_maxes_out_on_perfect_pair() -> None:
    r = _reg(number="INV-1", date_=date(2026, 6, 15), total=100_000)
    b = _b2b(number="INV-1", date_=date(2026, 6, 15), total=100_000)
    assert score_pair(r, b, CFG) == pytest.approx(1.0)
