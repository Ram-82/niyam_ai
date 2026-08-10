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


def test_ims_fields_passthrough_when_present() -> None:
    """IMS-era fields (``imsactn`` + ``imsts``) must reach the canonical
    entry unmodified when the payload carries them. Migration 0006 stores
    them on b2b_entry.ims_action / ims_status. No engine consumes them
    yet (see README 'IMS-era 2B semantics' TODO)."""
    payload = _sample_2b()
    inv0 = payload["data"]["docdata"]["b2b"][0]["inv"][0]
    inv0["imsactn"] = "A"
    inv0["imsts"] = "accepted"
    inv1 = payload["data"]["docdata"]["b2b"][0]["inv"][1]
    inv1["imsactn"] = "P"
    inv1["imsts"] = "pending"
    result = parse_gstr2b_json(payload, gstn_pull_id=PULL_ID)
    assert result.entries[0].ims_action == "A"
    assert result.entries[0].ims_status == "accepted"
    assert result.entries[1].ims_action == "P"
    assert result.entries[1].ims_status == "pending"


def test_ims_fields_null_when_absent() -> None:
    """Pre-IMS payloads (no imsactn/imsts) must yield None — never a
    bare empty string or 'None' literal that would land in the DB."""
    result = parse_gstr2b_json(_sample_2b(), gstn_pull_id=PULL_ID)
    assert result.entries[0].ims_action is None
    assert result.entries[0].ims_status is None


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


# ---------------------------------------------------------------------------
# CDNR section tests
# ---------------------------------------------------------------------------


def _sample_2b_with_cdnr() -> dict:
    payload = _sample_2b()
    payload["data"]["docdata"]["cdnr"] = [
        {
            "ctin": "27CCCCC5678D3Z5",
            "nt": [
                {
                    "ntty": "C",
                    "nt_num": "CN/001",
                    "nt_dt": "10-06-2026",
                    "itcavl": "Y",
                    "items": [
                        {
                            "rt": 18,
                            "txval": 500,
                            "iamt": 0,
                            "camt": 45,
                            "samt": 45,
                            "csamt": 0,
                        }
                    ],
                },
                {
                    "ntty": "D",
                    "nt_num": "DN/001",
                    "nt_dt": "12-06-2026",
                    "itcavl": "N",
                    "items": [
                        {
                            "rt": 18,
                            "txval": 200,
                            "iamt": 36,
                            "camt": 0,
                            "samt": 0,
                            "csamt": 0,
                        }
                    ],
                },
            ],
        }
    ]
    return payload


def test_cdnr_credit_note_parsed_correctly() -> None:
    result = parse_gstr2b_json(_sample_2b_with_cdnr(), gstn_pull_id=PULL_ID)
    cdn_entries = [e for e in result.entries if e.note_type is not None]
    credit_notes = [e for e in cdn_entries if e.note_type == "credit_note"]
    assert len(credit_notes) == 1
    cn = credit_notes[0]
    assert cn.supplier_gstin == "27CCCCC5678D3Z5"
    assert cn.invoice_number == "CN/001"
    assert cn.invoice_date == date(2026, 6, 10)
    assert cn.taxable_value_paise == 50_000
    assert cn.cgst_paise == 4_500
    assert cn.sgst_paise == 4_500
    assert cn.itc_available is True
    assert result.cdn_note_count == 2


def test_cdnr_debit_note_parsed_correctly() -> None:
    result = parse_gstr2b_json(_sample_2b_with_cdnr(), gstn_pull_id=PULL_ID)
    debit_notes = [e for e in result.entries if e.note_type == "debit_note"]
    assert len(debit_notes) == 1
    dn = debit_notes[0]
    assert dn.invoice_number == "DN/001"
    assert dn.igst_paise == 3_600
    assert dn.itc_available is False


def test_cdnr_entries_do_not_affect_invoice_count() -> None:
    """invoice_count must count only b2b invoices, not CDN notes."""
    result = parse_gstr2b_json(_sample_2b_with_cdnr(), gstn_pull_id=PULL_ID)
    assert result.invoice_count == 2
    assert result.cdn_note_count == 2
    assert len(result.entries) == 4  # 2 B2B + 2 CDN


def test_cdnr_absent_does_not_raise() -> None:
    """Payloads without cdnr are still valid — cdnr is optional in 2B."""
    result = parse_gstr2b_json(_sample_2b(), gstn_pull_id=PULL_ID)
    assert result.cdn_note_count == 0
    cdn_entries = [e for e in result.entries if e.note_type is not None]
    assert cdn_entries == []


def test_cdnr_bad_ntty_is_rejected() -> None:
    """A note with ntty other than C/D must be rejected, not crash."""
    payload = _sample_2b_with_cdnr()
    payload["data"]["docdata"]["cdnr"][0]["nt"][0]["ntty"] = "X"
    result = parse_gstr2b_json(payload, gstn_pull_id=PULL_ID)
    assert any(r.reason == "missing_required" for r in result.rejects)


def test_cdnr_b2b_note_types_are_null() -> None:
    """B2B invoice entries must always have note_type=None."""
    result = parse_gstr2b_json(_sample_2b_with_cdnr(), gstn_pull_id=PULL_ID)
    b2b_entries = [e for e in result.entries if e.note_type is None]
    assert len(b2b_entries) == 2
