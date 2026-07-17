"""Integration tests for validate_period.

Seeds a firm + gstin_profile + a handful of invoices (some clean, some
tripping specific rules), runs ``validate_period``, and asserts the
right ``validation_flag`` rows land — pinned to the active rule pack
version, respecting RLS, and idempotent on re-run.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.db import owner_engine
from app.engines.validation.gstin import compute_check_digit
from app.engines.validation.service import validate_period


def _valid_gstin(base: str) -> str:
    return base + compute_check_digit(base)


CLIENT_GSTIN = _valid_gstin("29AAAAA0000A1Z")   # Karnataka
GOOD_SUPPLIER = _valid_gstin("29BBBBB1234C2Z")  # Karnataka intra-state
INTER_STATE_SUPPLIER = _valid_gstin("27CCCCC5678D3Z")  # Maharashtra


@pytest.fixture
def firm_and_profile(bootstrap_firm):
    admin = bootstrap_firm(admin_email="validator@example.com")
    firm_id = admin["firm_id"]

    with owner_engine.begin() as conn:
        client_id = uuid.uuid4()
        gstin_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:c, :f, 'Val Client')"
            ),
            {"c": client_id, "f": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code) "
                "VALUES (:g, :f, :c, :gstin, '29')"
            ),
            {"g": gstin_id, "f": firm_id, "c": client_id, "gstin": CLIENT_GSTIN},
        )
    return firm_id, gstin_id


def _insert_invoice(
    firm_id, gstin_id, *, number, invoice_date, counterparty, taxable, cgst,
    sgst, igst, total, hsn=None
) -> uuid.UUID:
    """Owner-engine insert bypasses RLS so we can seed test data quickly."""
    invoice_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO invoice (
                    id, firm_id, gstin_profile_id, source, direction,
                    invoice_number, invoice_date, counterparty_gstin,
                    taxable_value_paise, cgst_paise, sgst_paise, igst_paise,
                    total_paise, hsn_sac, content_hash
                ) VALUES (
                    :id, :fid, :gid, 'csv_import', 'purchase',
                    :num, :dt, :cp,
                    :tx, :cgst, :sgst, :igst,
                    :total, :hsn, :hash
                )
                """
            ),
            {
                "id": invoice_id, "fid": firm_id, "gid": gstin_id,
                "num": number, "dt": invoice_date, "cp": counterparty,
                "tx": taxable, "cgst": cgst, "sgst": sgst, "igst": igst,
                "total": total, "hsn": hsn,
                "hash": f"h-{invoice_id}",
            },
        )
    return invoice_id


def _flags_by_rule(firm_id) -> dict[str, int]:
    with owner_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT rule_code, count(*) FROM validation_flag "
                "WHERE firm_id = :f GROUP BY rule_code"
            ),
            {"f": str(firm_id)},
        ).fetchall()
    return {r[0]: r[1] for r in rows}


def test_validate_period_writes_expected_flags(firm_and_profile) -> None:
    firm_id, gid = firm_and_profile

    # Clean invoice (should produce zero flags)
    _insert_invoice(
        firm_id, gid,
        number="INV-CLEAN", invoice_date=date(2026, 6, 15),
        counterparty=GOOD_SUPPLIER,
        taxable=100_000, cgst=9_000, sgst=9_000, igst=0, total=118_000,
        hsn="998311",
    )
    # Missing GSTIN -> R001 + R004 (missing HSN, warning)
    _insert_invoice(
        firm_id, gid,
        number="INV-NO-GSTIN", invoice_date=date(2026, 6, 20),
        counterparty=None,
        taxable=50_000, cgst=4_500, sgst=4_500, igst=0, total=59_000,
        hsn=None,
    )
    # Intra-state with IGST -> R005 + R006 (arithmetic mismatch)
    _insert_invoice(
        firm_id, gid,
        number="INV-BAD-HEAD", invoice_date=date(2026, 6, 25),
        counterparty=GOOD_SUPPLIER,
        taxable=100_000, cgst=0, sgst=0, igst=15_000, total=115_000,
        hsn="998311",
    )

    summary = validate_period(
        firm_id=firm_id,
        gstin_profile_id=gid,
        period="202606",
        today=date(2026, 7, 5),
    )

    assert summary.invoices_evaluated == 3
    assert summary.rule_pack_version == "1.0.0"
    assert summary.by_rule.get("R001", 0) >= 1
    assert summary.by_rule.get("R005", 0) >= 1

    counts = _flags_by_rule(firm_id)
    assert counts.get("R001", 0) == 1
    assert counts.get("R005", 0) == 1


def test_validate_period_is_idempotent(firm_and_profile) -> None:
    firm_id, gid = firm_and_profile
    _insert_invoice(
        firm_id, gid,
        number="INV-DUP-FLAG", invoice_date=date(2026, 6, 15),
        counterparty=None,  # -> R001
        taxable=50_000, cgst=4_500, sgst=4_500, igst=0, total=59_000,
        hsn="998311",
    )
    validate_period(firm_id, gid, "202606", today=date(2026, 7, 5))
    counts_after_first = _flags_by_rule(firm_id)
    validate_period(firm_id, gid, "202606", today=date(2026, 7, 5))
    counts_after_second = _flags_by_rule(firm_id)
    assert counts_after_first == counts_after_second


def test_validate_period_detects_duplicate_suspects(firm_and_profile) -> None:
    firm_id, gid = firm_and_profile
    # Two invoices with the same (counterparty, normalized number) in period.
    _insert_invoice(
        firm_id, gid,
        number="INV-001", invoice_date=date(2026, 6, 15),
        counterparty=GOOD_SUPPLIER,
        taxable=100_000, cgst=9_000, sgst=9_000, igst=0, total=118_000,
        hsn="998311",
    )
    _insert_invoice(
        firm_id, gid,
        number="inv 1", invoice_date=date(2026, 6, 20),   # different date/amount
        counterparty=GOOD_SUPPLIER,
        taxable=110_000, cgst=9_900, sgst=9_900, igst=0, total=129_800,
        hsn="998311",
    )
    validate_period(firm_id, gid, "202606", today=date(2026, 7, 5))
    counts = _flags_by_rule(firm_id)
    # Both invoices trip R007.
    assert counts.get("R007", 0) == 2


def test_validate_period_ignores_other_periods_and_other_firms(
    firm_and_profile, bootstrap_firm
) -> None:
    firm_id, gid = firm_and_profile

    # Invoice OUTSIDE period 202606 — should not be evaluated at all.
    _insert_invoice(
        firm_id, gid,
        number="INV-OTHER", invoice_date=date(2026, 5, 15),
        counterparty=None,
        taxable=1_000, cgst=90, sgst=90, igst=0, total=1_180,
        hsn=None,
    )
    # Set up another firm with a bad invoice — must not appear.
    other = bootstrap_firm(admin_email="other@example.com")
    with owner_engine.begin() as conn:
        oc = uuid.uuid4()
        og = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:c, :f, 'Other')"
            ),
            {"c": oc, "f": other["firm_id"]},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code) "
                "VALUES (:g, :f, :c, :gs, '27')"
            ),
            {
                "g": og,
                "f": other["firm_id"],
                "c": oc,
                "gs": _valid_gstin("27DDDDD1111E1Z"),
            },
        )
    _insert_invoice(
        other["firm_id"], og,
        number="INV-OTHER-FIRM", invoice_date=date(2026, 6, 20),
        counterparty=None,
        taxable=50_000, cgst=4_500, sgst=4_500, igst=0, total=59_000,
        hsn=None,
    )

    summary = validate_period(firm_id, gid, "202606", today=date(2026, 7, 5))
    assert summary.invoices_evaluated == 0  # in-period, in-firm: none

    # Firm A must have zero flags.
    counts = _flags_by_rule(firm_id)
    assert counts == {}
