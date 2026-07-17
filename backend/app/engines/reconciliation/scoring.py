"""Pair scoring for Pass 2 (fuzzy match).

A pair is fully disqualified (score = 0) when any hard gate fails:

* supplier GSTIN differs
* invoice_date distance > date_window_days
* amount distance > amount_tolerance_percent

Otherwise we compute a weighted score in [0, 1] from three components,
weighted by ``ReconConfig.fuzzy_score_weights``:

* ``number_similarity`` — SequenceMatcher ratio on normalized numbers.
  A perfect number match (same normalized string) is 1.0. Everything
  else falls off gracefully.
* ``date_closeness`` — 1.0 when dates coincide, linearly to 0 at the
  edge of the window.
* ``amount_closeness`` — 1.0 when amounts coincide, linearly to 0 at
  the edge of the tolerance.

The confidence is what lands in ``match_result.confidence`` and drives
the dashboard's confirm/reject UI.
"""
from __future__ import annotations

from difflib import SequenceMatcher

from app.engines.reconciliation.types import B2BLine, ReconConfig, RegisterLine


def score_pair(
    inv: RegisterLine, b2b: B2BLine, cfg: ReconConfig
) -> float:
    """Return a confidence in [0, 1], or 0 if a hard gate fails."""
    if inv.supplier_gstin != b2b.supplier_gstin:
        return 0.0

    date_diff = abs((inv.invoice_date - b2b.invoice_date).days)
    if date_diff > cfg.date_window_days:
        return 0.0

    amount_diff = abs(inv.total_paise - b2b.total_paise)
    # Percent tolerance is over the register total. Guard divide-by-zero.
    base = max(1, inv.total_paise)
    tolerance_paise = int(base * cfg.amount_tolerance_percent / 100.0)
    if amount_diff > tolerance_paise and amount_diff > 0:
        # Also allow exact-equal (both zero taxable, unlikely but harmless).
        if base != b2b.total_paise:
            return 0.0

    # -- Component scores --
    if inv.normalized_number == b2b.normalized_number:
        num_score = 1.0
    else:
        num_score = SequenceMatcher(
            None, inv.normalized_number, b2b.normalized_number
        ).ratio()

    if cfg.date_window_days <= 0:
        date_score = 1.0 if date_diff == 0 else 0.0
    else:
        date_score = 1.0 - (date_diff / cfg.date_window_days)

    if tolerance_paise <= 0:
        amount_score = 1.0 if amount_diff == 0 else 0.0
    else:
        amount_score = 1.0 - (amount_diff / tolerance_paise)
    amount_score = max(0.0, min(1.0, amount_score))

    w = cfg.fuzzy_score_weights
    total_w = w["number_similarity"] + w["date_closeness"] + w["amount_closeness"]
    if total_w <= 0:
        return 0.0
    return (
        w["number_similarity"] * num_score
        + w["date_closeness"] * date_score
        + w["amount_closeness"] * amount_score
    ) / total_w
