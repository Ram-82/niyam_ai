"""CSV parser for purchase/sales invoice imports.

Header contract (case-insensitive, extra columns ignored):

    invoice_number       required
    invoice_date         required — DD-MM-YYYY, DD/MM/YYYY, or YYYY-MM-DD
    counterparty_gstin   optional — flagged by validation rule R001 if missing
    taxable_value        required — rupees, up to 2 decimal places
    cgst                 optional (default 0)
    sgst                 optional (default 0)
    igst                 optional (default 0)
    total                required — rupees
    hsn_sac              optional

Rows with missing required fields, malformed dates, or non-numeric amounts
are collected as ``RejectedRow`` objects with the offending values. Rows
that survive parsing become ``CanonicalInvoice`` instances — the caller
handles content_hash dedup at INSERT time.

This is deliberately not a raw Tally XML parser. Real Tally exports use
XML and vary by version; converting Tally XML to this CSV shape is a
small bridge script Niyam ships separately (see README: "Tally bridge").
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable, Iterator, Optional

from app.ingestion.canonical import (
    CanonicalInvoice,
    normalize_invoice_number,
    rupees_to_paise,
)
from app.ingestion.errors import RejectedRow


REQUIRED_COLUMNS = ("invoice_number", "invoice_date", "taxable_value", "total")
OPTIONAL_COLUMNS = (
    "counterparty_gstin",
    "cgst",
    "sgst",
    "igst",
    "hsn_sac",
)
KNOWN_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS


@dataclass
class ParseResult:
    invoices: list[CanonicalInvoice]
    rejects: list[RejectedRow]


class SchemaError(Exception):
    """Header is missing required columns; the whole file is rejected."""


def _parse_date(raw: str) -> date:
    raw = (raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"invalid date: {raw!r}")


def _normalize_header(fieldname: str) -> str:
    # Excel-exported CSVs often prefix the first header with a UTF-8 BOM
    # (﻿). Strip it here so ``invoice_number`` still matches.
    return fieldname.lstrip("﻿").strip().lower().replace(" ", "_")


def parse_invoice_csv(
    text_stream: Iterable[str],
    gstin_profile_id: str,
    direction: str,
) -> ParseResult:
    """Parse a CSV file and return canonical invoices + rejects.

    ``text_stream`` can be any iterable of str lines — a StringIO, a
    file opened in text mode, or the result of decoding uploaded bytes.
    """
    reader = csv.DictReader(text_stream)
    if reader.fieldnames is None:
        raise SchemaError("CSV appears to be empty")

    # Normalize headers so ``Invoice Number`` and ``invoice_number`` both work.
    reader.fieldnames = [_normalize_header(f) for f in reader.fieldnames]

    missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
    if missing:
        raise SchemaError(
            f"CSV missing required columns: {', '.join(missing)}"
        )

    invoices: list[CanonicalInvoice] = []
    rejects: list[RejectedRow] = []

    for i, row in enumerate(reader, start=2):  # start=2 because row 1 is header
        raw = {k: (row.get(k) or "").strip() for k in KNOWN_COLUMNS if k in row}
        # Cheap required-field check
        for col in REQUIRED_COLUMNS:
            if not raw.get(col):
                rejects.append(
                    RejectedRow(
                        row_index=i,
                        reason="missing_required",
                        message=f"required field {col!r} is empty",
                        raw=raw,
                    )
                )
                break
        else:
            try:
                inv_date = _parse_date(raw["invoice_date"])
            except ValueError as e:
                rejects.append(
                    RejectedRow(
                        row_index=i, reason="bad_date", message=str(e), raw=raw
                    )
                )
                continue
            try:
                taxable = rupees_to_paise(raw["taxable_value"])
                cgst = rupees_to_paise(raw.get("cgst"))
                sgst = rupees_to_paise(raw.get("sgst"))
                igst = rupees_to_paise(raw.get("igst"))
                total = rupees_to_paise(raw["total"])
            except ValueError as e:
                rejects.append(
                    RejectedRow(
                        row_index=i, reason="bad_amount", message=str(e), raw=raw
                    )
                )
                continue

            invoice_number = raw["invoice_number"]
            counterparty = (raw.get("counterparty_gstin") or "").upper() or None
            hsn = raw.get("hsn_sac") or None

            invoices.append(
                CanonicalInvoice(
                    gstin_profile_id=gstin_profile_id,
                    direction=direction,
                    invoice_number=invoice_number,
                    invoice_date=inv_date,
                    counterparty_gstin=counterparty,
                    taxable_value_paise=taxable,
                    cgst_paise=cgst,
                    sgst_paise=sgst,
                    igst_paise=igst,
                    total_paise=total,
                    hsn_sac=hsn,
                    payload={
                        "source_row_index": i,
                        "normalized_number": normalize_invoice_number(invoice_number),
                    },
                )
            )

    return ParseResult(invoices=invoices, rejects=rejects)


def parse_invoice_csv_bytes(
    data: bytes,
    gstin_profile_id: str,
    direction: str,
    encoding: str = "utf-8",
) -> ParseResult:
    """Convenience wrapper for uploaded file bytes."""
    text = data.decode(encoding, errors="replace")
    return parse_invoice_csv(
        io.StringIO(text), gstin_profile_id=gstin_profile_id, direction=direction
    )
