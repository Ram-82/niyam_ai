"""GSTR-3B summary-return JSON generator.

Sections covered:
* 3.1(a)  — outward taxable supplies (other than zero-rated, nil, exempt)
* 4(A)(5) — All other ITC (eligible ITC from reconciled 2B)
* 6.1     — payment of tax (cash + credit split, computed simply as
            "pay net tax after ITC from cash")

Deliberately deferred (no data or too much ambiguity for MVP):
* 3.1(b)–(e) — zero-rated / nil-rated / non-GST — no capture yet
* 3.2       — inter-state to unregistered/composition — needs place_of_supply
* 4(A)(1)–(4) — import/reverse-charge sub-sections — no capture
* 4(B)      — ITC reversal — no data
* 5         — exempt inward supplies — no data
* Interest, late fee, DRC-03 — out of scope for a "pre-filing" tool

The ITC side reads only ``matched`` and CA-confirmed ``probable`` match
rows. ``supplier_default`` and ``missing_entry`` are the *purpose* of
this tool — surfacing them so the CA chases suppliers — and must NOT
land in ITC eligible until a match materialises.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.filings.types import to_gstn_period
from app.rules.default_pack import VERSION as RULE_PACK_VERSION


_PAISE_PER_RUPEE = Decimal(100)
_ZERO_2DP = Decimal("0.00")


def _paise_to_rupees(paise: int) -> float:
    q = (Decimal(paise) / _PAISE_PER_RUPEE).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return float(q)


def _sum_outward(db: Session, gid: str, period: str) -> dict[str, int]:
    """Total taxable + cgst/sgst/igst across active sale invoices in
    the period. Returns paise; caller converts to rupees."""
    yyyy_mm = f"{period[:4]}-{period[4:6]}"
    row = db.execute(
        text(
            """
            SELECT
                COALESCE(SUM(taxable_value_paise), 0) AS txval,
                COALESCE(SUM(cgst_paise), 0) AS cgst,
                COALESCE(SUM(sgst_paise), 0) AS sgst,
                COALESCE(SUM(igst_paise), 0) AS igst
            FROM invoice
            WHERE gstin_profile_id = :gid
              AND direction = 'sale'
              AND status = 'active'
              AND to_char(invoice_date, 'YYYY-MM') = :yyyy_mm
            """
        ),
        {"gid": gid, "yyyy_mm": yyyy_mm},
    ).one()
    return {
        "txval_paise": int(row.txval),
        "cgst_paise": int(row.cgst),
        "sgst_paise": int(row.sgst),
        "igst_paise": int(row.igst),
    }


def _sum_eligible_itc(db: Session, gid: str, period: str) -> dict[str, int]:
    """Sum tax_paise_breakdown across b2b_entry rows that landed in
    a ``matched`` bucket, plus ``probable`` rows the CA has confirmed.

    Rejected probables are excluded. Supplier_default and missing_entry
    are excluded by design — that's the whole point of the tool: chase
    them first, don't claim ITC on unmatched invoices.
    """
    row = db.execute(
        text(
            """
            SELECT
                COALESCE(SUM((b.tax_paise_breakdown->>'cgst')::BIGINT), 0) AS cgst,
                COALESCE(SUM((b.tax_paise_breakdown->>'sgst')::BIGINT), 0) AS sgst,
                COALESCE(SUM((b.tax_paise_breakdown->>'igst')::BIGINT), 0) AS igst
            FROM match_result m
            JOIN reconciliation_run r ON r.id = m.run_id
            JOIN b2b_entry b ON b.id = m.b2b_entry_id
            WHERE r.gstin_profile_id = :gid
              AND r.period = :period
              AND r.status = 'completed'
              AND b.itc_available = TRUE
              AND m.rejected = FALSE
              AND (
                m.bucket = 'matched'
                OR (m.bucket = 'probable' AND m.confirmed_by IS NOT NULL)
              )
            """
        ),
        {"gid": gid, "period": period},
    ).one()
    return {
        "cgst_paise": int(row.cgst),
        "sgst_paise": int(row.sgst),
        "igst_paise": int(row.igst),
    }


def _tax_paid_via_cash(outward: dict[str, int], itc: dict[str, int]) -> dict[str, int]:
    """Simple offset: cash pays whatever ITC doesn't cover, floored at 0.

    Real 3B ITC-cash cross-utilisation follows a legal ladder (IGST
    credit consumed first, then CGST/SGST separately, etc.) — we do NOT
    encode that yet. The CA will adjust in the portal. Being visibly
    naive here is safer than pretending to be authoritative and shipping
    a wrong number.
    """
    return {
        "cgst_paise": max(0, outward["cgst_paise"] - itc["cgst_paise"]),
        "sgst_paise": max(0, outward["sgst_paise"] - itc["sgst_paise"]),
        "igst_paise": max(0, outward["igst_paise"] - itc["igst_paise"]),
    }


def generate_gstr3b(
    db: Session,
    gstin_profile_id: str,
    period: str,
) -> dict[str, Any]:
    profile = db.execute(
        text(
            "SELECT gstin FROM gstin_profile WHERE id = :gid"
        ),
        {"gid": gstin_profile_id},
    ).one()

    outward = _sum_outward(db, gstin_profile_id, period)
    itc = _sum_eligible_itc(db, gstin_profile_id, period)
    cash = _tax_paid_via_cash(outward, itc)

    payload: dict[str, Any] = {
        "gstin": profile.gstin,
        "ret_period": to_gstn_period(period),
        # 3.1 Outward supplies
        "sup_details": {
            "osup_det": {
                "txval": _paise_to_rupees(outward["txval_paise"]),
                "iamt": _paise_to_rupees(outward["igst_paise"]),
                "camt": _paise_to_rupees(outward["cgst_paise"]),
                "samt": _paise_to_rupees(outward["sgst_paise"]),
                "csamt": 0.0,
            },
            "osup_zero": {"txval": 0.0, "iamt": 0.0, "csamt": 0.0},
            "osup_nil_exmp": {"txval": 0.0},
            "isup_rev": {"txval": 0.0, "iamt": 0.0, "camt": 0.0, "samt": 0.0, "csamt": 0.0},
            "osup_nongst": {"txval": 0.0},
        },
        # 4 ITC
        "itc_elg": {
            "itc_avl": [
                # Only 4(A)(5) — "all other ITC" — is populated. The other
                # sub-rows (import of goods, import of services, ISD,
                # reverse charge) require data we do not capture.
                {
                    "ty": "OTH",
                    "iamt": _paise_to_rupees(itc["igst_paise"]),
                    "camt": _paise_to_rupees(itc["cgst_paise"]),
                    "samt": _paise_to_rupees(itc["sgst_paise"]),
                    "csamt": 0.0,
                },
            ],
            "itc_rev": [],
            "itc_net": {
                "iamt": _paise_to_rupees(itc["igst_paise"]),
                "camt": _paise_to_rupees(itc["cgst_paise"]),
                "samt": _paise_to_rupees(itc["sgst_paise"]),
                "csamt": 0.0,
            },
            "itc_inelg": [],
        },
        # 6.1 Payment of tax (simplified cash-covers-shortfall model)
        "tx_pmt": {
            "tx_pd_cash": {
                "iamt": _paise_to_rupees(cash["igst_paise"]),
                "camt": _paise_to_rupees(cash["cgst_paise"]),
                "samt": _paise_to_rupees(cash["sgst_paise"]),
                "csamt": 0.0,
            },
            "tx_pd_itc": {
                "iamt": _paise_to_rupees(
                    min(outward["igst_paise"], itc["igst_paise"])
                ),
                "camt": _paise_to_rupees(
                    min(outward["cgst_paise"], itc["cgst_paise"])
                ),
                "samt": _paise_to_rupees(
                    min(outward["sgst_paise"], itc["sgst_paise"])
                ),
                "csamt": 0.0,
            },
        },
        "_meta": {
            "rule_pack_version": RULE_PACK_VERSION,
            "return_type": "GSTR3B",
            "period": period,
            "sections_covered": ["3.1(a)", "4(A)(5)", "6.1"],
            "sections_deferred": [
                "3.1(b)-(e)", "3.2", "4(A)(1)-(4)", "4(B)", "5",
                "interest", "late_fee",
            ],
            "itc_offset_model": "naive_cash_covers_shortfall",
        },
    }
    return payload
