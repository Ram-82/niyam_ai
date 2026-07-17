"""Unit tests for the invoice CSV parser."""
from __future__ import annotations

import io
from datetime import date

import pytest

from app.ingestion.csv_parser import (
    SchemaError,
    parse_invoice_csv,
    parse_invoice_csv_bytes,
)


HEADER = (
    "invoice_number,invoice_date,counterparty_gstin,taxable_value,"
    "cgst,sgst,igst,total,hsn_sac"
)


def _csv(rows: list[str]) -> str:
    return "\n".join([HEADER, *rows])


def test_happy_path() -> None:
    text = _csv(
        [
            "INV-001,15-06-2026,29ABCDE1234F1Z5,1000,90,90,0,1180,9983",
        ]
    )
    result = parse_invoice_csv(
        io.StringIO(text),
        gstin_profile_id="11111111-1111-1111-1111-111111111111",
        direction="purchase",
    )
    assert len(result.invoices) == 1
    assert len(result.rejects) == 0
    inv = result.invoices[0]
    assert inv.invoice_number == "INV-001"
    assert inv.invoice_date == date(2026, 6, 15)
    assert inv.counterparty_gstin == "29ABCDE1234F1Z5"
    assert inv.taxable_value_paise == 100_000
    assert inv.total_paise == 118_000
    assert inv.hsn_sac == "9983"


def test_rejects_bad_date() -> None:
    text = _csv(["INV-002,not-a-date,29ABCDE1234F1Z5,1000,90,90,0,1180,"])
    result = parse_invoice_csv(
        io.StringIO(text),
        gstin_profile_id="11111111-1111-1111-1111-111111111111",
        direction="purchase",
    )
    assert result.invoices == []
    assert len(result.rejects) == 1
    assert result.rejects[0].reason == "bad_date"
    assert result.rejects[0].row_index == 2  # 1-based, row 1 is header


def test_rejects_negative_amount() -> None:
    text = _csv(["INV-003,15-06-2026,,-1000,0,0,0,1180,"])
    result = parse_invoice_csv(
        io.StringIO(text),
        gstin_profile_id="11111111-1111-1111-1111-111111111111",
        direction="purchase",
    )
    assert result.invoices == []
    assert result.rejects[0].reason == "bad_amount"


def test_rejects_missing_required_field() -> None:
    # invoice_number empty
    text = _csv([",15-06-2026,29ABCDE1234F1Z5,1000,90,90,0,1180,"])
    result = parse_invoice_csv(
        io.StringIO(text),
        gstin_profile_id="11111111-1111-1111-1111-111111111111",
        direction="purchase",
    )
    assert result.invoices == []
    assert result.rejects[0].reason == "missing_required"


def test_schema_error_when_required_header_missing() -> None:
    # No taxable_value column
    bad_header = "invoice_number,invoice_date,total"
    text = "\n".join([bad_header, "INV-004,15-06-2026,1180"])
    with pytest.raises(SchemaError):
        parse_invoice_csv(
            io.StringIO(text),
            gstin_profile_id="11111111-1111-1111-1111-111111111111",
            direction="purchase",
        )


def test_bytes_wrapper_handles_utf8_bom() -> None:
    """Excel-exported CSVs prefix the first header cell with a UTF-8 BOM.
    ``_normalize_header`` strips it so ``invoice_number`` still matches."""
    text = "﻿" + _csv(["INV-005,15-06-2026,,1000,90,90,0,1180,"])
    result = parse_invoice_csv_bytes(
        text.encode("utf-8"),
        gstin_profile_id="11111111-1111-1111-1111-111111111111",
        direction="purchase",
    )
    assert len(result.invoices) == 1
    assert len(result.rejects) == 0
