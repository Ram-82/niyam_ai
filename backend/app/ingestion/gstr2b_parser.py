"""GSTR-2B JSON parser (b2b + cdnr sections).

The GSTN 2B JSON is nested and evolves periodically. P1 supports the two
common shapes seen in production exports:

    {"data": {"docdata": {"b2b": [{"ctin": ..., "inv": [...]}]}}}
    {"data": {"b2b":       [{"ctin": ..., "inv": [...]}]}}

The same nesting applies to the ``cdnr`` (credit/debit notes) section,
which uses ``nt[]`` instead of ``inv[]`` and carries ``ntty`` ("C"=credit,
"D"=debit) and ``nt_num``/``nt_dt`` in place of ``inum``/``idt``.

P1 parses both b2b and cdnr and stores them as ``b2b_entry`` rows with
``note_type=NULL`` (b2b) or ``'credit_note'/'debit_note'`` (cdnr). The
reconciliation engine skips cdnr rows (``WHERE note_type IS NULL``) — the
CDN adjustment is informational in P1: the ITC summary is labeled
"before credit/debit note adjustments."

Not handled in P1:

* ``b2ba`` (amendments), ``cdnra`` (credit/debit note amendments)
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
    cdn_note_count: int = 0


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


def _find_cdnr_section(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the cdnr list, or [] if the section is absent (cdnr is optional)."""
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    for candidate in (data.get("docdata"), data):
        if isinstance(candidate, dict):
            cdnr = candidate.get("cdnr")
            if isinstance(cdnr, list):
                return cdnr
    return []


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

            # IMS passthrough — carry the GSTN fields to storage without
            # interpreting them. Both are optional; pre-IMS payloads omit.
            ims_action_raw = inv.get("imsactn")
            ims_status_raw = inv.get("imsts")
            ims_action = str(ims_action_raw).strip() if ims_action_raw else None
            ims_status = str(ims_status_raw).strip() if ims_status_raw else None

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
                    ims_status=ims_status,
                    ims_action=ims_action,
                )
            )

    # --- CDNR section (credit / debit notes) --------------------------------
    cdnr = _find_cdnr_section(payload)
    cdn_note_count = 0
    for ci, supplier in enumerate(cdnr):
        ctin = str(supplier.get("ctin") or "").upper()
        notes = supplier.get("nt") or []
        if not ctin or not isinstance(notes, list):
            rejects.append(
                RejectedRow(
                    row_index=ci,
                    reason="schema",
                    message="cdnr supplier block missing ctin or nt[]",
                    raw={"path": f"cdnr[{ci}]", "keys": list(supplier.keys())},
                )
            )
            continue
        for ni, note in enumerate(notes):
            cdn_note_count += 1
            path = f"cdnr[{ci}].nt[{ni}]"
            ntty = str(note.get("ntty") or "").upper()
            nt_num = note.get("nt_num")
            nt_dt = note.get("nt_dt")
            if not nt_num or not nt_dt or ntty not in ("C", "D"):
                rejects.append(
                    RejectedRow(
                        row_index=cdn_note_count,
                        reason="missing_required",
                        message="cdnr note missing nt_num, nt_dt, or ntty (C/D)",
                        raw={"path": path, "supplier_gstin": ctin},
                    )
                )
                continue
            try:
                note_date = _parse_2b_date(nt_dt)
            except ValueError as e:
                rejects.append(
                    RejectedRow(
                        row_index=cdn_note_count,
                        reason="bad_date",
                        message=str(e),
                        raw={"path": path, "supplier_gstin": ctin},
                    )
                )
                continue

            items = note.get("items") or []
            try:
                txval, cgst, sgst, igst, cess = _sum_items_or_invoice(note, items)
            except ValueError as e:
                rejects.append(
                    RejectedRow(
                        row_index=cdn_note_count,
                        reason="bad_amount",
                        message=str(e),
                        raw={"path": path, "supplier_gstin": ctin},
                    )
                )
                continue

            note_type = "credit_note" if ntty == "C" else "debit_note"
            itc_flag = str(note.get("itcavl") or "Y").upper() == "Y"
            ims_action_raw = note.get("imsactn")
            ims_status_raw = note.get("imsts")
            ims_action = str(ims_action_raw).strip() if ims_action_raw else None
            ims_status = str(ims_status_raw).strip() if ims_status_raw else None

            entries.append(
                CanonicalB2BEntry(
                    gstn_pull_id=gstn_pull_id,
                    supplier_gstin=ctin,
                    invoice_number=str(nt_num),
                    invoice_date=note_date,
                    taxable_value_paise=txval,
                    cgst_paise=cgst,
                    sgst_paise=sgst,
                    igst_paise=igst,
                    cess_paise=cess,
                    itc_available=itc_flag,
                    note_type=note_type,
                    ims_status=ims_status,
                    ims_action=ims_action,
                )
            )

    return B2BParseResult(
        entries=entries,
        rejects=rejects,
        period=period,
        ctin_count=len(b2b),
        invoice_count=invoice_count,
        cdn_note_count=cdn_note_count,
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
