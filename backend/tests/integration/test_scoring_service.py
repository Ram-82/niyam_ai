"""End-to-end scoring test.

Seeds a firm + gstin_profile + invoices + a completed reconciliation_run,
runs ``compute_and_persist``, and asserts:

* ``readiness_snapshot`` row is inserted (append-only) with the right
  score, blockers, arithmetic, rule_pack_version.
* Blockers carry paise_impact from the recon summary (command-center
  sort key).
* Re-running APPENDS another row (not UPDATE — the append-only trigger
  from migration 0001 would raise).
"""
from __future__ import annotations

import json
import uuid
from datetime import date

import pytest
from sqlalchemy import text

from app.db import owner_engine
from app.engines.reconciliation.service import reconcile_period
from app.engines.scoring.service import compute_and_persist
from app.engines.validation.gstin import compute_check_digit
from app.engines.validation.service import validate_period


def _gstin(base: str) -> str:
    return base + compute_check_digit(base)


CLIENT_GSTIN = _gstin("29AAAAA0000A1Z")
SUP_A = _gstin("29BBBBB1234C2Z")
SUP_B = _gstin("27CCCCC5678D3Z")


@pytest.fixture
def firm_gid(bootstrap_firm):
    admin = bootstrap_firm(admin_email="scorer@example.com")
    firm_id = admin["firm_id"]
    gid = uuid.uuid4()
    with owner_engine.begin() as conn:
        cid = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:c, :f, 'Scorer Client')"
            ),
            {"c": cid, "f": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code, scheme) "
                "VALUES (:g, :f, :c, :gs, '29', 'regular')"
            ),
            {"g": gid, "f": firm_id, "c": cid, "gs": CLIENT_GSTIN},
        )
    return firm_id, gid


def _insert_invoice(
    firm_id, gid, *, number, date_, cp, total, hsn="998311", cgst=0, sgst=0, igst=0
) -> uuid.UUID:
    invoice_id = uuid.uuid4()
    taxable = total - cgst - sgst - igst
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO invoice (
                    id, firm_id, gstin_profile_id, source, direction,
                    invoice_number, invoice_date, counterparty_gstin,
                    taxable_value_paise, cgst_paise, sgst_paise,
                    igst_paise, total_paise, hsn_sac, content_hash
                ) VALUES (
                    :id, :f, :g, 'csv_import', 'purchase',
                    :num, :dt, :cp,
                    :tx, :cgst, :sgst, :igst, :total, :hsn, :h
                )
                """
            ),
            {
                "id": invoice_id, "f": firm_id, "g": gid,
                "num": number, "dt": date_, "cp": cp,
                "tx": taxable, "cgst": cgst, "sgst": sgst, "igst": igst,
                "total": total, "hsn": hsn, "h": f"h-{invoice_id}",
            },
        )
    return invoice_id


def _seed_2b(firm_id, gid, *, period, entries):
    pull_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO gstn_pull (id, firm_id, gstin_profile_id,
                    return_type, period, raw_payload, source)
                VALUES (:id, :f, :g, 'GSTR2B', :p, CAST('{}' AS JSONB),
                    'json_import')
                """
            ),
            {"id": pull_id, "f": firm_id, "g": gid, "p": period},
        )
        for e in entries:
            conn.execute(
                text(
                    """
                    INSERT INTO b2b_entry (
                        firm_id, gstn_pull_id, supplier_gstin,
                        invoice_number, invoice_date,
                        taxable_value_paise, tax_paise_breakdown,
                        itc_available
                    ) VALUES (
                        :f, :pid, :ctin, :inum, :idt, :tx,
                        CAST(:tb AS JSONB), TRUE
                    )
                    """
                ),
                {
                    "f": firm_id, "pid": pull_id, "ctin": e["supplier"],
                    "inum": e["number"], "idt": e["date"], "tx": e["taxable"],
                    "tb": json.dumps(e.get("breakdown", {"cgst": 0, "sgst": 0, "igst": 0, "cess": 0})),
                },
            )


# ---------------------------------------------------------------------------
# Happy path with real recon data
# ---------------------------------------------------------------------------


def test_compute_and_persist_produces_snapshot_and_blockers(firm_gid) -> None:
    firm_id, gid = firm_gid
    # 3 register invoices totalling ₹300k. 1 matched, 1 supplier_default.
    _insert_invoice(
        firm_id, gid, number="M-1", date_=date(2026, 6, 15),
        cp=SUP_A, total=100_000,
    )
    _insert_invoice(
        firm_id, gid, number="SD-1", date_=date(2026, 6, 20),
        cp=SUP_B, total=200_000,
    )
    _seed_2b(
        firm_id, gid, period="202606",
        entries=[
            {"supplier": SUP_A, "number": "M-1",
             "date": date(2026, 6, 15), "taxable": 100_000},
            # GHOST — no register counterpart → missing_entry
            {"supplier": SUP_A, "number": "GHOST-1",
             "date": date(2026, 6, 18), "taxable": 5_000},
        ],
    )
    reconcile_period(firm_id, gid, "202606")

    result = compute_and_persist(
        firm_id, gid, return_type="GSTR1", period="202606",
        today=date(2026, 7, 5),
    )

    assert 0 <= result.score <= 100
    assert result.rule_pack_version == "1.0.0"

    codes = {b["code"] for b in result.blockers}
    assert "SUPPLIER_DEFAULT_TOTAL" in codes
    assert "MISSING_ENTRY_TOTAL" in codes

    # paise_impact for supplier_default should be 200_000 (SD-1 total)
    sd_blocker = next(b for b in result.blockers if b["code"] == "SUPPLIER_DEFAULT_TOTAL")
    assert sd_blocker["paise_impact"] == 200_000

    # missing_entry blocker owned by client, paise = 5000
    me = next(b for b in result.blockers if b["code"] == "MISSING_ENTRY_TOTAL")
    assert me["owner"] == "client"
    assert me["paise_impact"] == 5_000

    # Row landed
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT score, rule_pack_version, arithmetic "
                "FROM readiness_snapshot WHERE id = :id"
            ),
            {"id": str(result.snapshot_id)},
        ).mappings().first()
    assert row["score"] == result.score
    assert row["rule_pack_version"] == "1.0.0"
    assert row["arithmetic"]["final_score"] == result.score


def test_repeated_compute_appends_a_new_snapshot(firm_gid) -> None:
    firm_id, gid = firm_gid
    _insert_invoice(
        firm_id, gid, number="M-1", date_=date(2026, 6, 15),
        cp=SUP_A, total=100_000,
    )
    _seed_2b(
        firm_id, gid, period="202606",
        entries=[{"supplier": SUP_A, "number": "M-1",
                  "date": date(2026, 6, 15), "taxable": 100_000}],
    )
    reconcile_period(firm_id, gid, "202606")

    r1 = compute_and_persist(firm_id, gid, "GSTR1", "202606", today=date(2026, 7, 5))
    r2 = compute_and_persist(firm_id, gid, "GSTR1", "202606", today=date(2026, 7, 6))
    assert r1.snapshot_id != r2.snapshot_id

    with owner_engine.begin() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM readiness_snapshot "
                "WHERE gstin_profile_id = :g AND period = '202606'"
            ),
            {"g": str(gid)},
        ).scalar()
    assert count == 2


def test_validation_errors_lower_the_score(firm_gid) -> None:
    firm_id, gid = firm_gid
    # Missing-GSTIN invoice → R001 error
    _insert_invoice(
        firm_id, gid, number="BAD-1", date_=date(2026, 6, 15),
        cp=None, total=50_000, hsn=None,
    )
    _seed_2b(firm_id, gid, period="202606", entries=[])
    # Run validation so an error row exists on validation_flag.
    validate_period(firm_id, gid, "202606", today=date(2026, 7, 5))

    # Recon run required for scoring (else it uses an empty summary — still OK).
    # But 2B is empty, so recon raises NoTwoBPull. Insert a dummy pull first:
    _seed_2b(firm_id, gid, period="202606", entries=[])
    reconcile_period(firm_id, gid, "202606")

    r_bad = compute_and_persist(
        firm_id, gid, "GSTR1", "202606", today=date(2026, 7, 5)
    )
    # A validation error blocker should surface.
    codes = {b["code"] for b in r_bad.blockers}
    assert "VALIDATION_ERRORS" in codes
    assert 0 <= r_bad.score < 100


def test_rls_isolates_snapshot_reads_across_firms(firm_gid, bootstrap_firm) -> None:
    firm_a, gid_a = firm_gid
    # Write firm A snapshot
    _insert_invoice(
        firm_a, gid_a, number="A-1", date_=date(2026, 6, 15),
        cp=SUP_A, total=10_000,
    )
    _seed_2b(
        firm_a, gid_a, period="202606",
        entries=[{"supplier": SUP_A, "number": "A-1",
                  "date": date(2026, 6, 15), "taxable": 10_000}],
    )
    reconcile_period(firm_a, gid_a, "202606")
    compute_and_persist(firm_a, gid_a, "GSTR1", "202606", today=date(2026, 7, 5))

    # Firm B setup
    admin_b = bootstrap_firm(admin_email="b@ex.com")
    firm_b = admin_b["firm_id"]
    gid_b = uuid.uuid4()
    with owner_engine.begin() as conn:
        cid = uuid.uuid4()
        conn.execute(
            text("INSERT INTO client (id, firm_id, trade_name) VALUES (:c, :f, 'B')"),
            {"c": cid, "f": firm_b},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code, scheme) "
                "VALUES (:g, :f, :c, :gs, '27', 'regular')"
            ),
            {"g": gid_b, "f": firm_b, "c": cid, "gs": _gstin("27DDDDD1111E1Z")},
        )

    # From firm B's scope, count readiness_snapshot rows for firm A's gid.
    from app.db import firm_scoped_session
    with firm_scoped_session(firm_b) as s:
        n = s.execute(
            text(
                "SELECT count(*) FROM readiness_snapshot "
                "WHERE gstin_profile_id = :g"
            ),
            {"g": str(gid_a)},
        ).scalar()
    assert n == 0
