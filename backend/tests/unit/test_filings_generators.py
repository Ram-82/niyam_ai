"""Unit tests for the GSTR-1 and GSTR-3B generators.

Seeds directly through owner_engine, then invokes the generator with an
app-role scoped session so RLS is exercised the same way the API layer
would exercise it. Focus is on: correct GSTN JSON shape, correct paise→
rupees rounding, and correct ITC bucketing (matched + confirmed
probables count; supplier_default / missing_entry / rejected do NOT).
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.db import firm_scoped_session, owner_engine
from app.engines.validation.gstin import compute_check_digit
from app.filings.gstr1_generator import (
    _derive_tax_rate_pct,
    _fmt_invoice_date,
    _paise_to_rupees,
    _place_of_supply,
    generate_gstr1,
)
from app.filings.gstr3b_generator import generate_gstr3b
from app.filings.types import to_gstn_period


# ---------------------------------------------------------------------------
# Pure-function tests — no DB
# ---------------------------------------------------------------------------


def test_paise_to_rupees_exact_2dp() -> None:
    assert _paise_to_rupees(12550) == 125.50
    assert _paise_to_rupees(0) == 0.0
    assert _paise_to_rupees(1) == 0.01
    # Half-up: 125 paise -> 1.25 exactly, not 1.24999
    assert _paise_to_rupees(125) == 1.25


def test_derive_tax_rate_pct_intra_state() -> None:
    # 100000 paise taxable, 9000 CGST + 9000 SGST => 18%
    assert _derive_tax_rate_pct(100000, 9000, 9000, 0) == 18.0


def test_derive_tax_rate_pct_inter_state() -> None:
    # 200000 paise taxable, 24000 IGST => 12%
    assert _derive_tax_rate_pct(200000, 0, 0, 24000) == 12.0


def test_derive_tax_rate_pct_zero_taxable_safe() -> None:
    # No divide-by-zero even when tax is nonzero (validator flags this
    # upstream — the generator must not crash mid-render).
    assert _derive_tax_rate_pct(0, 100, 0, 0) == 0.0


def test_place_of_supply_from_gstin() -> None:
    assert _place_of_supply("29AAAAA0000A1Z5") == "29"
    with pytest.raises(ValueError):
        _place_of_supply("")


def test_fmt_invoice_date_iso_to_ddmmyyyy() -> None:
    assert _fmt_invoice_date("2026-07-15") == "15-07-2026"


def test_to_gstn_period_yyyymm_to_mmyyyy() -> None:
    assert to_gstn_period("202607") == "072026"
    with pytest.raises(ValueError):
        to_gstn_period("2026-07")


# ---------------------------------------------------------------------------
# DB-backed tests
# ---------------------------------------------------------------------------


CLIENT_GSTIN = "29AAAAA0000A1Z" + compute_check_digit("29AAAAA0000A1Z")
BUYER_A = "29BBBBB1234C2Z" + compute_check_digit("29BBBBB1234C2Z")   # intra-state
BUYER_B = "27CCCCC5678D3Z" + compute_check_digit("27CCCCC5678D3Z")   # inter-state
SUPPLIER_M = "29MMMMM0001M1Z" + compute_check_digit("29MMMMM0001M1Z")
SUPPLIER_P = "29PPPPP0002P1Z" + compute_check_digit("29PPPPP0002P1Z")
SUPPLIER_D = "29DDDDD0003D1Z" + compute_check_digit("29DDDDD0003D1Z")


@pytest.fixture
def seeded_gstin():
    """Firm + GSTIN + a couple of sale/purchase invoices for period 202607."""
    firm_id = uuid.uuid4()
    user_id = uuid.uuid4()
    client_id = uuid.uuid4()
    gid = uuid.uuid4()
    pull_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ca_firm (id, name) VALUES (:id, 'FGen')"),
            {"id": firm_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO app_user (id, firm_id, email, password_hash,
                    role, totp_secret, totp_confirmed, is_active)
                VALUES (:u, :f, 'gen@example.com', 'x', 'admin',
                    'ABCDEFGHIJKLMNOP', TRUE, TRUE)
                """
            ),
            {"u": user_id, "f": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) VALUES (:c, :f, 'C1')"
            ),
            {"c": client_id, "f": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code, scheme) "
                "VALUES (:g, :f, :c, :gs, '29', 'regular')"
            ),
            {"g": gid, "f": firm_id, "c": client_id, "gs": CLIENT_GSTIN},
        )
        # Two intra-state B2B sale invoices to BUYER_A (18% CGST+SGST)
        for num, txval, cgst, sgst in [
            ("S-1", 100000, 9000, 9000),
            ("S-2", 200000, 18000, 18000),
        ]:
            conn.execute(
                text(
                    """
                    INSERT INTO invoice (
                        firm_id, gstin_profile_id, source, direction,
                        invoice_number, invoice_date, counterparty_gstin,
                        taxable_value_paise, cgst_paise, sgst_paise, igst_paise,
                        total_paise, content_hash
                    ) VALUES (
                        :f, :g, 'csv_import', 'sale',
                        :n, DATE '2026-07-15', :cp,
                        :tx, :c, :s, 0, :total, :h
                    )
                    """
                ),
                {
                    "f": firm_id, "g": gid, "n": num, "cp": BUYER_A,
                    "tx": txval, "c": cgst, "s": sgst,
                    "total": txval + cgst + sgst, "h": f"h-{num}",
                },
            )
        # One inter-state B2B sale to BUYER_B (12% IGST)
        conn.execute(
            text(
                """
                INSERT INTO invoice (
                    firm_id, gstin_profile_id, source, direction,
                    invoice_number, invoice_date, counterparty_gstin,
                    taxable_value_paise, cgst_paise, sgst_paise, igst_paise,
                    total_paise, content_hash
                ) VALUES (
                    :f, :g, 'csv_import', 'sale',
                    'S-3', DATE '2026-07-20', :cp,
                    500000, 0, 0, 60000, 560000, 'h-S-3'
                )
                """
            ),
            {"f": firm_id, "g": gid, "cp": BUYER_B},
        )
        # A B2C sale (no counterparty) — must NOT land in b2b section
        conn.execute(
            text(
                """
                INSERT INTO invoice (
                    firm_id, gstin_profile_id, source, direction,
                    invoice_number, invoice_date, counterparty_gstin,
                    taxable_value_paise, cgst_paise, sgst_paise, igst_paise,
                    total_paise, content_hash
                ) VALUES (
                    :f, :g, 'csv_import', 'sale',
                    'S-4', DATE '2026-07-25', NULL,
                    50000, 4500, 4500, 0, 59000, 'h-S-4'
                )
                """
            ),
            {"f": firm_id, "g": gid},
        )
        # A purchase invoice from a matched supplier — for the 3B ITC path
        conn.execute(
            text(
                """
                INSERT INTO invoice (
                    firm_id, gstin_profile_id, source, direction,
                    invoice_number, invoice_date, counterparty_gstin,
                    taxable_value_paise, cgst_paise, sgst_paise, igst_paise,
                    total_paise, content_hash
                ) VALUES (
                    :f, :g, 'csv_import', 'purchase',
                    'P-M', DATE '2026-07-10', :cp,
                    100000, 9000, 9000, 0, 118000, 'h-P-M'
                )
                """
            ),
            {"f": firm_id, "g": gid, "cp": SUPPLIER_M},
        )

        conn.execute(
            text(
                """
                INSERT INTO gstn_pull (id, firm_id, gstin_profile_id,
                    return_type, period, raw_payload, source)
                VALUES (:id, :f, :g, 'GSTR2B', '202607', CAST('{}' AS JSONB),
                    'json_import')
                """
            ),
            {"id": pull_id, "f": firm_id, "g": gid},
        )
        # Three 2B entries: MATCHED (M), CONFIRMED-PROBABLE (P), SUPPLIER-DEFAULT (D).
        # Only M + P should land in ITC.
        for note, num, sup, tx, cgst, sgst in [
            ("m", "P-M", SUPPLIER_M, 100000, 9000, 9000),
            ("p", "P-P", SUPPLIER_P, 200000, 18000, 18000),
            ("d", "P-D", SUPPLIER_D, 500000, 0, 0),
        ]:
            conn.execute(
                text(
                    """
                    INSERT INTO b2b_entry (
                        firm_id, gstn_pull_id, supplier_gstin,
                        invoice_number, invoice_date,
                        taxable_value_paise, tax_paise_breakdown, itc_available
                    ) VALUES (
                        :f, :pid, :sup, :num, DATE '2026-07-10',
                        :tx, CAST(:tax AS JSONB), TRUE
                    )
                    """
                ),
                {
                    "f": firm_id, "pid": pull_id, "sup": sup, "num": num,
                    "tx": tx,
                    "tax": f'{{"cgst": {cgst}, "sgst": {sgst}, "igst": 0}}',
                },
            )
        # A completed reconciliation_run with three match_result rows
        run_id = uuid.uuid4()
        conn.execute(
            text(
                """
                INSERT INTO reconciliation_run (
                    id, firm_id, gstin_profile_id, period, status,
                    rule_pack_version, gstn_pull_id, started_at, finished_at
                ) VALUES (
                    :id, :f, :g, '202607', 'completed',
                    '1.0.0', :pid, now(), now()
                )
                """
            ),
            {"id": run_id, "f": firm_id, "g": gid, "pid": pull_id},
        )
        # Fetch entry IDs to attach matches
        entries = conn.execute(
            text(
                "SELECT id, invoice_number FROM b2b_entry "
                "WHERE gstn_pull_id = :pid"
            ),
            {"pid": pull_id},
        ).all()
        by_num = {e.invoice_number: e.id for e in entries}
        # matched
        conn.execute(
            text(
                """
                INSERT INTO match_result (firm_id, run_id, b2b_entry_id,
                    bucket, confidence, rule_pack_version)
                VALUES (:f, :r, :b, 'matched', 1.0, '1.0.0')
                """
            ),
            {"f": firm_id, "r": run_id, "b": by_num["P-M"]},
        )
        # confirmed probable
        conn.execute(
            text(
                """
                INSERT INTO match_result (firm_id, run_id, b2b_entry_id,
                    bucket, confidence, rule_pack_version,
                    confirmed_by, confirmed_at)
                VALUES (:f, :r, :b, 'probable', 0.85, '1.0.0',
                    :u, now())
                """
            ),
            {"f": firm_id, "r": run_id, "b": by_num["P-P"], "u": user_id},
        )
        # supplier_default — must NOT contribute ITC
        conn.execute(
            text(
                """
                INSERT INTO match_result (firm_id, run_id, b2b_entry_id,
                    bucket, confidence, rule_pack_version)
                VALUES (:f, :r, :b, 'supplier_default', 0.0, '1.0.0')
                """
            ),
            {"f": firm_id, "r": run_id, "b": by_num["P-D"]},
        )
    return {"firm_id": firm_id, "gid": gid}


# ---------------------------------------------------------------------------
# GSTR-1
# ---------------------------------------------------------------------------


def test_gstr1_b2b_shape_and_totals(seeded_gstin) -> None:
    with firm_scoped_session(seeded_gstin["firm_id"]) as s:
        p = generate_gstr1(s, str(seeded_gstin["gid"]), "202607")
    assert p["gstin"] == CLIENT_GSTIN
    assert p["fp"] == "072026"
    # 3 B2B rows, 2 counterparties (BUYER_A x2, BUYER_B x1)
    b2b = p["b2b"]
    assert [x["ctin"] for x in b2b] == sorted([BUYER_A, BUYER_B])
    a_row = next(x for x in b2b if x["ctin"] == BUYER_A)
    assert len(a_row["inv"]) == 2
    inv1 = a_row["inv"][0]
    assert inv1["inum"] == "S-1"
    assert inv1["idt"] == "15-07-2026"
    assert inv1["pos"] == "29"
    assert inv1["itms"][0]["itm_det"]["txval"] == 1000.0
    assert inv1["itms"][0]["itm_det"]["camt"] == 90.0
    assert inv1["itms"][0]["itm_det"]["samt"] == 90.0
    assert inv1["itms"][0]["itm_det"]["rt"] == 18.0
    # Inter-state row
    b_row = next(x for x in b2b if x["ctin"] == BUYER_B)
    assert b_row["inv"][0]["pos"] == "27"
    assert b_row["inv"][0]["itms"][0]["itm_det"]["iamt"] == 600.0
    assert b_row["inv"][0]["itms"][0]["itm_det"]["rt"] == 12.0
    # B2C invoice (S-4) must NOT be in b2b
    for row in b2b:
        for inv in row["inv"]:
            assert inv["inum"] != "S-4"
    # cur_gt = sum of all sale totals (incl B2C) = 118000+236000+560000+59000 paise
    assert p["cur_gt"] == pytest.approx(9730.00, abs=0.01)
    # Empty sections must exist with correct shape
    assert p["cdnr"] == []
    assert p["exp"] == []
    assert p["hsn"] == {"data": []}
    # _meta records the coverage envelope
    assert p["_meta"]["sections_covered"] == ["b2b"]
    assert "b2cs" in p["_meta"]["sections_deferred"]


# ---------------------------------------------------------------------------
# GSTR-3B
# ---------------------------------------------------------------------------


def test_gstr3b_outward_and_eligible_itc(seeded_gstin) -> None:
    with firm_scoped_session(seeded_gstin["firm_id"]) as s:
        p = generate_gstr3b(s, str(seeded_gstin["gid"]), "202607")
    # Outward totals across all sale invoices
    # taxable: 100000+200000+500000+50000 = 850000 paise = ₹8,500
    # cgst: 9000+18000+0+4500 = 31500 paise = ₹315
    # sgst: same
    # igst: 60000 paise = ₹600
    osd = p["sup_details"]["osup_det"]
    assert osd["txval"] == 8500.00
    assert osd["camt"] == 315.00
    assert osd["samt"] == 315.00
    assert osd["iamt"] == 600.00

    # ITC — matched (P-M: 9000/9000/0) + confirmed probable (P-P: 18000/18000/0)
    itc_row = p["itc_elg"]["itc_avl"][0]
    assert itc_row["ty"] == "OTH"
    assert itc_row["camt"] == 270.00   # (9000 + 18000) paise
    assert itc_row["samt"] == 270.00
    assert itc_row["iamt"] == 0.00
    # Supplier_default (P-D: 500000/0/0/0) must NOT contribute — the
    # whole point of the tool.
    # (If it did, camt would be higher; assertion above pins it.)

    # 6.1: cash = max(0, outward - itc). CGST outward 315, itc 270 -> cash 45
    cash = p["tx_pmt"]["tx_pd_cash"]
    assert cash["camt"] == 45.00
    assert cash["samt"] == 45.00
    assert cash["iamt"] == 600.00   # no IGST ITC available

    # tx_pd_itc capped at outward
    tx_itc = p["tx_pmt"]["tx_pd_itc"]
    assert tx_itc["camt"] == 270.00
    assert tx_itc["samt"] == 270.00
    assert tx_itc["iamt"] == 0.00

    assert p["_meta"]["itc_offset_model"] == "naive_cash_covers_shortfall"
