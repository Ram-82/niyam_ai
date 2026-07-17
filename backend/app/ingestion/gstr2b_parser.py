"""GSTR-2B JSON parser (b2b section only for P1).

The GSTN 2B JSON is nested and evolves periodically. P1 supports the two
common shapes seen in production exports:

    {"data": {"docdata": {"b2b": [{"ctin": ..., "inv": [...]}]}}}
    {"data": {"b2b":       [{"ctin": ..., "inv": [...]}]}}

Each supplier block carries ``ctin`` (supplier GSTIN) and ``inv[]``. Each
``inv`` carries invoice-level fields + an ``items[]`` list with tax
breakdown. We sum items to get per-invoice CGST/SGST/IGST/CESS in paise.

Not handled in P1:

* ``b2ba`` (amendments), ``cdnr``/``cdnra`` (credit/debit notes) — see the
  README Domain verification list. Every P1 ITC summary is labeled
  "before credit/debit note adjustments."
* ``impg`` (imports), ``impgsez``, ``isd`` sections.

Rejects are collected with row-index semantics: for a nested JSON the
"row index" is a dotted path like ``b2b[3].inv[1]`` so the CA can locate
the offending record in the source file.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.ingestion.canonical import CanonicalB2BEntry, rupees_to_paise
from app.ingestion.errors import RejectedRow


@dataclass
class B2BParseResult:
    entries: list[CanonicalB2BEntry]
    rejects: list[RejectedRow]
    period: str | None
    ctin_count: int
    invoice_count: int


class SchemaError(Exception):
    """The top-level JSON does not look like a GSTR-2B document at all."""


def _parse_2b_date(raw: str) -> date:
    raw = (raw or "").strip()
    for fmt in ("%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"invalid date: {raw!r}")


def _find_b2b_section(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        raise SchemaError("missing top-level 'data' object")
    for candidate in (data.get("docdata"), data):
        if isinstance(candidate, dict):
            b2b = candidate.get("b2b")
            if isinstance(b2b, list):
                return b2b
    raise SchemaError("no 'b2b' list found under data.docdata.b2b or data.b2b")


def _extract_period(payload: dict[str, Any]) -> str | None:
    """GSTR-2B carries a ``rtnprd`` field like ``'062026'`` (MM-YYYY)
    at various nesting depths. Convert to our canonical YYYYMM.
    """
    for parent in ("data", None):
        node = payload if parent is None else payload.get(parent)
        if isinstance(node, dict):
            rtnprd = node.get("rtnprd") or node.get("period")
            if isinstance(rtnprd, str) and len(rtnprd) == 6 and rtnprd.isdigit():
                # GSTN uses MMYYYY; we store YYYYMM.
                mm, yyyy = rtnprd[:2], rtnprd[2:]
                return f"{yyyy}{mm}"
    return None


def parse_gstr2b_json(
    payload: dict[str, Any],
    gstn_pull_id: str,
) -> B2BParseResult:
    """Convert a parsed 2B JSON to canonical B2B entries."""
    b2b = _find_b2b_section(payload)
    period = _extract_period(payload)

    entries: list[CanonicalB2BEntry] = []
    rejects: list[RejectedRow] = []
    invoice_count = 0

    for ci, supplier in enumerate(b2b):
        ctin = str(supplier.get("ctin") or "").upper()
        invs = supplier.get("inv") or []
        if not ctin or not isinstance(invs, list):
            rejects.append(
                RejectedRow(
                    row_index=ci,
                    reason="schema",
                    message="supplier block missing ctin or inv[]",
                    raw={"path": f"b2b[{ci}]", "keys": list(supplier.keys())},
                )
            )
            continue
        for ii, inv in enumerate(invs):
            invoice_count += 1
            path = f"b2b[{ci}].inv[{ii}]"
            inum = inv.get("inum")
            idt = inv.get("idt")
            if not inum or not idt:
                rejects.append(
                    RejectedRow(
                        row_index=invoice_count,
                        reason="missing_required",
                        message="invoice missing inum or idt",
                        raw={"path": path, "supplier_gstin": ctin},
                    )
                )
                continue
            try:
                inv_date = _parse_2b_date(idt)
            except ValueError as e:
                rejects.append(
                    RejectedRow(
                        row_index=invoice_count,
                        reason="bad_date",
                        message=str(e),
                        raw={"path": path, "supplier_gstin": ctin},
                    )
                )
                continue

            items = inv.get("items") or []
            try:
                txval, cgst, sgst, igst, cess = _sum_items_or_invoice(inv, items)
            except ValueError as e:
                rejects.append(
                    RejectedRow(
                        row_index=invoice_count,
                        reason="bad_amount",
                        message=str(e),
                        raw={"path": path, "supplier_gstin": ctin},
                    )
                )
                continue

            itc_flag = str(inv.get("itcavl") or "Y").upper() == "Y"

            entries.append(
                CanonicalB2BEntry(
                    gstn_pull_id=gstn_pull_id,
                    supplier_gstin=ctin,
                    invoice_number=str(inum),
                    invoice_date=inv_date,
                    taxable_value_paise=txval,
                    cgst_paise=cgst,
                    sgst_paise=sgst,
                    igst_paise=igst,
                    cess_paise=cess,
                    itc_available=itc_flag,
                    note_type=None,  # CDN handled in P2
                )
            )

    return B2BParseResult(
        entries=entries,
        rejects=rejects,
        period=period,
        ctin_count=len(b2b),
        invoice_count=invoice_count,
    )


def _sum_items_or_invoice(
    inv: dict[str, Any], items: list[dict[str, Any]]
) -> tuple[int, int, int, int, int]:
    """Return (taxable, cgst, sgst, igst, cess) in paise.

    Sums the item breakdown when present; falls back to invoice-level
    ``val``/``iamt``/``camt``/``samt``/``csamt`` when items are omitted (2B
    JSON sometimes ships without the items array).
    """
    if items:
        txval = sum(rupees_to_paise(it.get("txval")) for it in items)
        cgst = sum(rupees_to_paise(it.get("camt")) for it in items)
        sgst = sum(rupees_to_paise(it.get("samt")) for it in items)
        igst = sum(rupees_to_paise(it.get("iamt")) for it in items)
        cess = sum(rupees_to_paise(it.get("csamt")) for it in items)
        return txval, cgst, sgst, igst, cess
    return (
        rupees_to_paise(inv.get("val")),
        rupees_to_paise(inv.get("camt")),
        rupees_to_paise(inv.get("samt")),
        rupees_to_paise(inv.get("iamt")),
        rupees_to_paise(inv.get("csamt")),
    )


def parse_gstr2b_bytes(data: bytes, gstn_pull_id: str) -> B2BParseResult:
    """Convenience wrapper for uploaded file bytes."""
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise SchemaError(f"invalid JSON: {e}") from e
    return parse_gstr2b_json(payload, gstn_pull_id=gstn_pull_id)
