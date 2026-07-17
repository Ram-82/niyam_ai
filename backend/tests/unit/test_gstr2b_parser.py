"""Unit tests for the GSTR-2B JSON parser."""
from __future__ import annotations

import json
from datetime import date

import pytest

from app.ingestion.gstr2b_parser import (
    SchemaError,
    parse_gstr2b_bytes,
    parse_gstr2b_json,
)


PULL_ID = "11111111-1111-1111-1111-111111111111"


def _sample_2b() -> dict:
    return {
        "data": {
            "rtnprd": "062026",  # MMYYYY, we normalize to 202606
            "docdata": {
                "b2b": [
                    {
                        "ctin": "29AAAAA0000A1Z5",
                        "inv": [
                            {
                                "inum": "INV-100",
                                "idt": "15-06-2026",
                                "val": 1180,
                                "itcavl": "Y",
                                "items": [
                                    {
                                        "rt": 18,
                                        "txval": 1000,
                                        "iamt": 0,
                                        "camt": 90,
                                        "samt": 90,
                                        "csamt": 0,
                                    }
                                ],
                            },
                            {
                                "inum": "INV-101",
                                "idt": "20-06-2026",
                                "val": 2360,
                                "itcavl": "N",
                                "items": [
                                    {
                                        "rt": 18,
                                        "txval": 2000,
                                        "iamt": 360,
                                        "camt": 0,
                                        "samt": 0,
                                        "csamt": 0,
                                    }
                                ],
                            },
                        ],
                    }
                ]
            },
        }
    }


def test_happy_path_parses_two_invoices() -> None:
    result = parse_gstr2b_json(_sample_2b(), gstn_pull_id=PULL_ID)
    assert result.period == "202606"
    assert result.ctin_count == 1
    assert result.invoice_count == 2
    assert len(result.entries) == 2
    assert len(result.rejects) == 0

    a, b = result.entries
    assert a.supplier_gstin == "29AAAAA0000A1Z5"
    assert a.invoice_number == "INV-100"
    assert a.invoice_date == date(2026, 6, 15)
    assert a.taxable_value_paise == 100_000
    assert a.cgst_paise == 9_000
    assert a.sgst_paise == 9_000
    assert a.igst_paise == 0
    assert a.itc_available is True
    assert a.note_type is None

    assert b.igst_paise == 36_000
    assert b.itc_available is False


def test_missing_inum_is_rejected_not_raised() -> None:
    payload = _sample_2b()
    del payload["data"]["docdata"]["b2b"][0]["inv"][0]["inum"]
    result = parse_gstr2b_json(payload, gstn_pull_id=PULL_ID)
    assert len(result.entries) == 1
    assert len(result.rejects) == 1
    assert result.rejects[0].reason == "missing_required"


def test_alternate_top_level_shape() -> None:
    """Some 2B exports place ``b2b`` directly under ``data`` (no ``docdata``)."""
    payload = {
        "data": {
            "b2b": _sample_2b()["data"]["docdata"]["b2b"],
        }
    }
    result = parse_gstr2b_json(payload, gstn_pull_id=PULL_ID)
    assert len(result.entries) == 2


def test_falls_back_to_invoice_level_amounts_when_items_missing() -> None:
    payload = _sample_2b()
    inv = payload["data"]["docdata"]["b2b"][0]["inv"][0]
    inv.pop("items")
    inv.update({"camt": 90, "samt": 90, "iamt": 0, "csamt": 0})
    result = parse_gstr2b_json(payload, gstn_pull_id=PULL_ID)
    assert result.entries[0].cgst_paise == 9_000


def test_top_level_missing_data_raises() -> None:
    with pytest.raises(SchemaError):
        parse_gstr2b_json({"foo": "bar"}, gstn_pull_id=PULL_ID)


def test_bytes_wrapper_rejects_invalid_json() -> None:
    with pytest.raises(SchemaError):
        parse_gstr2b_bytes(b"{not valid json", gstn_pull_id=PULL_ID)


def test_bytes_wrapper_happy_path() -> None:
    data = json.dumps(_sample_2b()).encode("utf-8")
    result = parse_gstr2b_bytes(data, gstn_pull_id=PULL_ID)
    assert len(result.entries) == 2
