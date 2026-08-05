"""Three-pass reconciliation over register vs GSTR-2B.

Pass 1 EXACT — group both sides by exact key (supplier + normalized
    number + date). Within each key group, enumerate all (register,
    2B) pairs whose amount is within ``exact_amount_tolerance_paise``,
    sort by |amount_diff| ascending (deterministic tie-break on ids),
    and greedy-assign 1:1. This closest-amount pairing prevents the
    "two invoices with same number but different amounts" trap where
    first-in-wins would silently cross-pair them.

Pass 2 FUZZY — for the unmatched, score every remaining cross-pair,
    sort by score desc, greedily accept above threshold with 1:1
    assignment.

Pass 3 RESIDUALS — anything still unpaired becomes supplier_default
    (register side) or missing_entry (2B side). Each supplier_default
    is enriched with same-supplier ``NearMiss`` candidates from
    remaining 2B entries — the CA sees them before drafting any chase.
"""
from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from uuid import UUID

from app.engines.reconciliation.scoring import score_pair
from app.engines.reconciliation.types import (
    B2BLine,
    MatchPair,
    NearMiss,
    ReconConfig,
    ReconResult,
    RegisterLine,
    Residual,
)


NEAR_MISS_MIN_SIMILARITY = 0.5
NEAR_MISS_MAX_PER_RESIDUAL = 3


def reconcile(
    register: list[RegisterLine],
    b2b: list[B2BLine],
    cfg: ReconConfig,
) -> ReconResult:
    """Run all three passes and return a ReconResult."""
    result = ReconResult()

    remaining_reg = list(register)
    remaining_b2b = list(b2b)

    # ---------- Pass 1: EXACT ----------
    paired_reg, paired_b2b = _pass_exact(remaining_reg, remaining_b2b, cfg, result)
    remaining_reg = [r for r in remaining_reg if r.invoice_id not in paired_reg]
    remaining_b2b = [b for b in remaining_b2b if b.b2b_entry_id not in paired_b2b]

    # ---------- Pass 2: FUZZY ----------
    paired_reg, paired_b2b = _pass_fuzzy(remaining_reg, remaining_b2b, cfg, result)
    remaining_reg = [r for r in remaining_reg if r.invoice_id not in paired_reg]
    remaining_b2b = [b for b in remaining_b2b if b.b2b_entry_id not in paired_b2b]

    # ---------- Pass 3: RESIDUALS ----------
    _pass_residuals(remaining_reg, remaining_b2b, result)
    return result


# ---------------------------------------------------------------------------
# Pass 1 — EXACT (closest-amount pairing within same-key groups)
# ---------------------------------------------------------------------------


def _pass_exact(
    register: list[RegisterLine],
    b2b: list[B2BLine],
    cfg: ReconConfig,
    result: ReconResult,
) -> tuple[set[UUID], set[UUID]]:
    """Closest-amount greedy pairing per exact key group.

    Two register invoices with the same (supplier, number, date) MUST NOT
    cross-pair with 2B entries of different amounts just because of
    insertion order. Within each key group we enumerate all in-tolerance
    (reg, b2b) pairs, sort by |amount_diff| ascending, and greedy-pick.
    """
    b2b_by_key: dict[tuple[str, str, str], list[B2BLine]] = defaultdict(list)
    for b in b2b:
        key = (b.supplier_gstin, b.normalized_number, b.invoice_date.isoformat())
        b2b_by_key[key].append(b)

    reg_by_key: dict[tuple[str, str, str], list[RegisterLine]] = defaultdict(list)
    for r in register:
        key = (r.supplier_gstin, r.normalized_number, r.invoice_date.isoformat())
        reg_by_key[key].append(r)

    paired_reg: set[UUID] = set()
    paired_b2b: set[UUID] = set()

    # Iterate keys in a deterministic order so runs are reproducible.
    for key in sorted(reg_by_key.keys()):
        regs = reg_by_key[key]
        candidates = b2b_by_key.get(key, [])
        if not candidates:
            continue
        # Enumerate all in-tolerance pairs.
        pairs: list[tuple[int, RegisterLine, B2BLine]] = []
        for r in regs:
            for c in candidates:
                diff = abs(r.total_paise - c.total_paise)
                if diff <= cfg.exact_amount_tolerance_paise:
                    pairs.append((diff, r, c))
        # Sort: smallest diff first; deterministic tie-break on ids.
        pairs.sort(
            key=lambda t: (
                t[0],
                str(t[1].invoice_id),
                str(t[2].b2b_entry_id),
            )
        )
        for diff, r, c in pairs:
            if r.invoice_id in paired_reg or c.b2b_entry_id in paired_b2b:
                continue
            result.pairs.append(
                MatchPair(
                    invoice_id=r.invoice_id,
                    b2b_entry_id=c.b2b_entry_id,
                    bucket="matched",
                    confidence=1.0,
                    invoice_total_paise=r.total_paise,
                    b2b_total_paise=c.total_paise,
                    supplier_gstin=r.supplier_gstin,
                    itc_available=c.itc_available,
                )
            )
            paired_reg.add(r.invoice_id)
            paired_b2b.add(c.b2b_entry_id)
    return paired_reg, paired_b2b


# ---------------------------------------------------------------------------
# Pass 2 — FUZZY
# ---------------------------------------------------------------------------


def _pass_fuzzy(
    register: list[RegisterLine],
    b2b: list[B2BLine],
    cfg: ReconConfig,
    result: ReconResult,
) -> tuple[set[UUID], set[UUID]]:
    """Score every remaining cross-pair, greedy 1:1 above threshold."""
    scored: list[tuple[float, RegisterLine, B2BLine]] = []
    for r in register:
        for b in b2b:
            s = score_pair(r, b, cfg)
            if s >= cfg.probable_confidence_threshold:
                scored.append((s, r, b))

    scored.sort(
        key=lambda triple: (
            -triple[0],
            str(triple[1].invoice_id),
            str(triple[2].b2b_entry_id),
        )
    )

    paired_reg: set[UUID] = set()
    paired_b2b: set[UUID] = set()

    for score, r, b in scored:
        if r.invoice_id in paired_reg or b.b2b_entry_id in paired_b2b:
            continue
        result.pairs.append(
            MatchPair(
                invoice_id=r.invoice_id,
                b2b_entry_id=b.b2b_entry_id,
                bucket="probable",
                confidence=round(score, 4),
                invoice_total_paise=r.total_paise,
                b2b_total_paise=b.total_paise,
                supplier_gstin=r.supplier_gstin,
                itc_available=b.itc_available,
            )
        )
        paired_reg.add(r.invoice_id)
        paired_b2b.add(b.b2b_entry_id)
    return paired_reg, paired_b2b


# ---------------------------------------------------------------------------
# Pass 3 — RESIDUALS (with near-miss enrichment on supplier_default)
# ---------------------------------------------------------------------------


def _pass_residuals(
    remaining_reg: list[RegisterLine],
    remaining_b2b: list[B2BLine],
    result: ReconResult,
) -> None:
    for r in remaining_reg:
        near = _find_near_misses(r, remaining_b2b)
        result.residuals.append(
            Residual(
                bucket="supplier_default",
                invoice_id=r.invoice_id,
                b2b_entry_id=None,
                total_paise=r.total_paise,
                supplier_gstin=r.supplier_gstin,
                near_misses=near,
            )
        )
    for b in remaining_b2b:
        result.residuals.append(
            Residual(
                bucket="missing_entry",
                invoice_id=None,
                b2b_entry_id=b.b2b_entry_id,
                total_paise=b.total_paise,
                supplier_gstin=b.supplier_gstin,
            )
        )


def _find_near_misses(
    r: RegisterLine, unmatched_b2b: list[B2BLine]
) -> tuple[NearMiss, ...]:
    """Same-supplier 2B entries with normalized-number similarity above
    ``NEAR_MISS_MIN_SIMILARITY``. Ordered by similarity desc, capped."""
    candidates: list[tuple[float, B2BLine]] = []
    for b in unmatched_b2b:
        if b.supplier_gstin != r.supplier_gstin:
            continue
        if r.normalized_number == b.normalized_number:
            sim = 1.0
        else:
            sim = SequenceMatcher(
                None, r.normalized_number, b.normalized_number
            ).ratio()
        if sim < NEAR_MISS_MIN_SIMILARITY:
            continue
        candidates.append((sim, b))
    candidates.sort(key=lambda t: (-t[0], str(t[1].b2b_entry_id)))
    return tuple(
        NearMiss(
            b2b_entry_id=b.b2b_entry_id,
            supplier_gstin=b.supplier_gstin,
            invoice_number=b.invoice_number,
            invoice_date=b.invoice_date,
            total_paise=b.total_paise,
            similarity=round(sim, 4),
        )
        for sim, b in candidates[:NEAR_MISS_MAX_PER_RESIDUAL]
    )
