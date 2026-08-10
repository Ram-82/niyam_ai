"""Dataclasses shared by the reconciliation passes.

The algorithm never touches the DB — it works on plain dataclasses
(``RegisterLine`` for purchase invoices, ``B2BLine`` for GSTR-2B entries)
and returns a ``ReconResult``. ``service.py`` handles the DB round-trip
in both directions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional
from uuid import UUID


@dataclass(frozen=True)
class ReconConfig:
    exact_amount_tolerance_paise: int
    date_window_days: int
    amount_tolerance_percent: float
    probable_confidence_threshold: float
    fuzzy_score_weights: dict[str, float]  # keys: number_similarity, date_closeness, amount_closeness


@dataclass(frozen=True)
class RegisterLine:
    """A purchase invoice we already normalized in ingestion."""
    invoice_id: UUID
    supplier_gstin: str
    invoice_number: str          # raw as recorded
    normalized_number: str       # normalize_invoice_number(invoice_number)
    invoice_date: date
    total_paise: int             # taxable + all taxes on the register side


@dataclass(frozen=True)
class B2BLine:
    """A 2B row from the latest gstn_pull."""
    b2b_entry_id: UUID
    supplier_gstin: str
    invoice_number: str
    normalized_number: str
    invoice_date: date
    total_paise: int             # taxable + all tax components summed
    itc_available: bool


@dataclass(frozen=True)
class MatchPair:
    invoice_id: UUID
    b2b_entry_id: UUID
    bucket: str                  # 'matched' | 'probable'
    confidence: float
    # Register-side total; what the CA sees as "reconciled ITC" for this pair.
    invoice_total_paise: int
    b2b_total_paise: int
    supplier_gstin: str
    # Threaded from B2BLine so the summary can split matched ITC into
    # claimable vs not-available (respects the 2B ``itcavl`` flag). A
    # matched row with itc_available=False is NOT claimable ITC; it is
    # reconciled but the CA cannot claim credit against it.
    itc_available: bool = True


@dataclass(frozen=True)
class NearMiss:
    """A same-supplier 2B entry that scored below the probable threshold
    but is close enough that the CA should review before treating the
    residual as a real supplier default."""
    b2b_entry_id: UUID
    supplier_gstin: str
    invoice_number: str
    invoice_date: date
    total_paise: int
    similarity: float  # 0..1 — from difflib.SequenceMatcher on normalized number


@dataclass(frozen=True)
class Residual:
    """A one-sided leftover.

    * ``supplier_default``: register invoice with no 2B counterpart.
      The name is a legacy DB-level identifier — the *cause* could be:
      register-side error (typo, wrong period), a timing gap (supplier
      files later), or the supplier genuinely defaulted. CA-facing copy
      must not accuse the supplier before ``near_misses`` are reviewed.
    * ``missing_entry``: 2B entry with no register counterpart
      (unrecorded purchase — client-side data quality).
    """
    bucket: str
    invoice_id: Optional[UUID]
    b2b_entry_id: Optional[UUID]
    total_paise: int
    supplier_gstin: str
    near_misses: tuple[NearMiss, ...] = ()  # populated for supplier_default


@dataclass
class ReconResult:
    pairs: list[MatchPair] = field(default_factory=list)
    residuals: list[Residual] = field(default_factory=list)
    cdn_count: int = 0
    cdn_paise: int = 0

    def summary(self) -> dict[str, Any]:
        """Bucket counts + paise + top-offending suppliers for supplier_default."""
        matched = [p for p in self.pairs if p.bucket == "matched"]
        probable = [p for p in self.pairs if p.bucket == "probable"]
        sup_def = [r for r in self.residuals if r.bucket == "supplier_default"]
        missing = [r for r in self.residuals if r.bucket == "missing_entry"]

        # Aggregate top-offending suppliers by at-risk ITC.
        supplier_totals: dict[str, dict[str, int]] = {}
        for r in sup_def:
            s = supplier_totals.setdefault(
                r.supplier_gstin, {"count": 0, "paise": 0}
            )
            s["count"] += 1
            s["paise"] += r.total_paise

        top_suppliers = sorted(
            (
                {"supplier_gstin": g, **stats}
                for g, stats in supplier_totals.items()
            ),
            key=lambda x: x["paise"],
            reverse=True,
        )[:10]

        with_near_misses = sum(1 for r in sup_def if r.near_misses)
        matched_claimable = sum(
            p.invoice_total_paise for p in matched if p.itc_available
        )
        matched_not_available = sum(
            p.invoice_total_paise for p in matched if not p.itc_available
        )
        probable_claimable = sum(
            p.invoice_total_paise for p in probable if p.itc_available
        )
        probable_not_available = sum(
            p.invoice_total_paise for p in probable if not p.itc_available
        )
        return {
            "matched": {
                "count": len(matched),
                "paise": sum(p.invoice_total_paise for p in matched),
                # Stage-3 split: respects the 2B itcavl flag. IMS-era 2B
                # can carry ITC-blocked invoices (e.g. blocked-credit rule)
                # that reconcile to a register row but cannot be claimed.
                # UI must show ``paise_claimable`` in the ITC total and
                # surface ``paise_not_available`` as a distinct callout.
                "paise_claimable": matched_claimable,
                "paise_not_available": matched_not_available,
                # TODO-VERIFY-WITH-CA: README item 15 (adversarial fixture A10).
                # If the CA rules that a CGST+SGST-vs-IGST split at equal totals
                # must demote to `probable` or carry a warning, this is the
                # summary shape to extend (add `tax_split_warnings: int` etc.).
                "description": "exact match with a 2B entry",
            },
            "probable": {
                "count": len(probable),
                "paise": sum(p.invoice_total_paise for p in probable),
                "paise_claimable": probable_claimable,
                "paise_not_available": probable_not_available,
                "description": (
                    "fuzzy match above threshold — CA confirm/reject needed"
                ),
            },
            "supplier_default": {
                "count": len(sup_def),
                "paise": sum(r.total_paise for r in sup_def),
                "top_suppliers": top_suppliers,
                "with_near_misses": with_near_misses,
                # Deliberately non-accusatory copy — the bucket name is a
                # legacy DB identifier and does NOT imply the supplier failed
                # to file. See NearMiss + docs.
                "description": (
                    "no 2B match found — could be a register-side error "
                    "(typo/wrong period), a timing gap (supplier files later), "
                    "or a genuine supplier default. Review near_misses on "
                    "each row before drafting any supplier chase."
                ),
            },
            "missing_entry": {
                "count": len(missing),
                "paise": sum(r.total_paise for r in missing),
                "description": (
                    "2B entry with no register counterpart — likely an "
                    "unrecorded purchase; record before filing"
                ),
            },
            "cdn": {
                "count": self.cdn_count,
                "paise": self.cdn_paise,
                "description": (
                    "credit/debit notes from 2B — not yet applied to ITC. "
                    "Full CDN adjustment is a P2 feature."
                ),
            },
            "disclaimer": (
                "ITC figures are before credit/debit note adjustments. "
                f"{self.cdn_count} CDN note(s) parsed from 2B; "
                "not yet deducted from claimable ITC."
            ),
        }
