"""GSTR-1 outward-supplies JSON generator.

Produces the ``b2b`` section of the GSTN uploaded-JSON spec. B2CS, CDNR,
CDNUR, EXP, AT, ATADJ, HSN, NIL, DOC_ISSUE are scaffolded as empty
containers — they need data we don't capture yet (place_of_supply for
B2C, credit/debit note markers on outward invoices, shipping bills for
exports, HSN cleanup). Fill them in later; do not fabricate.

Money conversion: internal storage is paise (int); GSTN expects rupees
as a decimal number rounded to 2 places. We use Decimal + ROUND_HALF_UP
so `12550 paise` renders exactly as `125.50`, never `125.5` and never
`125.4999999`. Floats would silently drift.

Place-of-supply: derived from the counterparty GSTIN's leading 2-digit
state code (matches GSTN's own convention). No new columns needed.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.filings.types import to_gstn_period
from app.rules.default_pack import VERSION as RULE_PACK_VERSION


_PAISE_PER_RUPEE = Decimal(100)
_ZERO_2DP = Decimal("0.00")


def _paise_to_rupees(paise: int) -> float:
    """Return paise as rupees with exact 2-dp rounding.

    Uses Decimal so the JSON payload never carries binary-float artefacts
    like ``125.49999999999999``. GSTN validates decimal precision; a
    drift here is a rejected upload.
    """
    q = (Decimal(paise) / _PAISE_PER_RUPEE).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    # json.dumps renders Decimal as string, so cast to float here — the
    # 2-dp quantisation already made it representable.
    return float(q)


def _derive_tax_rate_pct(
    taxable_paise: int,
    cgst_paise: int,
    sgst_paise: int,
    igst_paise: int,
) -> float:
    """Infer the tax rate the invoice was raised at.

    For intra-state supplies, ``cgst + sgst`` equals the total tax; for
    inter-state, ``igst`` does. Rate = total_tax / taxable * 100. Rounded
    to 2 dp to match the rule pack's expected slabs [0, 0.1, 0.25, 3, 5,
    12, 18, 28].

    Returns ``0.0`` when taxable is 0 — safer than a divide-by-zero;
    downstream schema still accepts a zero-rate line item, and the
    validator's tax-arithmetic rule (r006) will have already surfaced
    the zero-taxable-with-nonzero-tax case.
    """
    if taxable_paise <= 0:
        return 0.0
    total_tax = cgst_paise + sgst_paise + igst_paise
    rate = (Decimal(total_tax) * 100 / Decimal(taxable_paise)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return float(rate)


def _place_of_supply(counterparty_gstin: str) -> str:
    """Two-digit state code from a 15-char GSTIN."""
    if not counterparty_gstin or len(counterparty_gstin) < 2:
        raise ValueError(
            f"cannot derive place_of_supply from GSTIN {counterparty_gstin!r}"
        )
    return counterparty_gstin[:2]


def _fmt_invoice_date(iso_date: str) -> str:
    """GSTN uses DD-MM-YYYY, not ISO."""
    y, m, d = iso_date.split("-")
    return f"{d}-{m}-{y}"


def generate_gstr1(
    db: Session,
    gstin_profile_id: str,
    period: str,
) -> dict[str, Any]:
    """Produce the GSTR-1 JSON payload for one (gstin, period).

    Reads only active outward (sale) invoices dated inside the period.
    B2C, CDNR and everything else are emitted as empty containers so the
    payload shape matches GSTN's schema even when we have no data for
    those sections.
    """
    profile = db.execute(
        text(
            "SELECT gstin, state_code FROM gstin_profile "
            "WHERE id = :gid"
        ),
        {"gid": gstin_profile_id},
    ).one()

    period_prefix = f"{period[:4]}-{period[4:6]}"
    rows = db.execute(
        text(
            """
            SELECT
                invoice_number, invoice_date, counterparty_gstin,
                taxable_value_paise, cgst_paise, sgst_paise, igst_paise,
                total_paise
            FROM invoice
            WHERE gstin_profile_id = :gid
              AND direction = 'sale'
              AND status = 'active'
              AND to_char(invoice_date, 'YYYY-MM') = :yyyy_mm
            ORDER BY invoice_date, invoice_number
            """
        ),
        {"gid": gstin_profile_id, "yyyy_mm": period_prefix},
    ).all()

    # Group by counterparty GSTIN. Skip rows without a counterparty
    # (those are B2C and belong in a section we do not yet emit).
    by_ctin: dict[str, list[Any]] = defaultdict(list)
    cur_gt = Decimal("0.00")
    for r in rows:
        if r.counterparty_gstin:
            by_ctin[r.counterparty_gstin].append(r)
        cur_gt += Decimal(str(_paise_to_rupees(r.total_paise)))

    b2b: list[dict[str, Any]] = []
    for ctin, inv_rows in by_ctin.items():
        invoices: list[dict[str, Any]] = []
        for r in inv_rows:
            rate = _derive_tax_rate_pct(
                r.taxable_value_paise, r.cgst_paise, r.sgst_paise, r.igst_paise
            )
            invoices.append({
                "inum": r.invoice_number,
                "idt": _fmt_invoice_date(r.invoice_date.isoformat()),
                "val": _paise_to_rupees(r.total_paise),
                "pos": _place_of_supply(ctin),
                "rchrg": "N",
                "inv_typ": "R",
                "itms": [
                    {
                        "num": 1,
                        "itm_det": {
                            "txval": _paise_to_rupees(r.taxable_value_paise),
                            "rt": rate,
                            "camt": _paise_to_rupees(r.cgst_paise),
                            "samt": _paise_to_rupees(r.sgst_paise),
                            "iamt": _paise_to_rupees(r.igst_paise),
                            "csamt": 0.0,
                        },
                    }
                ],
            })
        b2b.append({"ctin": ctin, "inv": invoices})

    # Deterministic order — GSTN doesn't care but our snapshot tests do.
    b2b.sort(key=lambda x: x["ctin"])

    payload: dict[str, Any] = {
        "gstin": profile.gstin,
        "fp": to_gstn_period(period),
        "gt": 0.0,             # gross turnover of preceding FY — unknown for MVP
        "cur_gt": float(cur_gt.quantize(_ZERO_2DP, rounding=ROUND_HALF_UP)),
        "b2b": b2b,
        # Scaffolded empty sections — schema-shaped, data-free. Do NOT
        # populate these from guessed sources; each needs its own data
        # capture pass.
        "b2cl": [],
        "b2cs": [],
        "cdnr": [],
        "cdnur": [],
        "exp": [],
        "at": [],
        "atadj": [],
        "hsn": {"data": []},
        "nil": {},
        "doc_issue": {},
        "_meta": {
            "rule_pack_version": RULE_PACK_VERSION,
            "return_type": "GSTR1",
            "period": period,
            "sections_covered": ["b2b"],
            "sections_deferred": [
                "b2cl", "b2cs", "cdnr", "cdnur", "exp",
                "at", "atadj", "hsn", "nil", "doc_issue",
            ],
        },
    }
    return payload
