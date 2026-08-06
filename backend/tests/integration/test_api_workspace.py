"""Workspace API tests — flag resolve, match confirm/reject, engine
triggers, and audit_log wiring on every mutation.

Uses the full stack: bootstrap firm → seed invoices + 2B → login →
call the workspace endpoints → assert DB state + audit_log rows.
"""
from __future__ import annotations

import json
import uuid
from datetime import date

import pyotp
import pytest
from sqlalchemy import text

from app.db import owner_engine
from app.engines.validation.gstin import compute_check_digit


def _gstin(base: str) -> str:
    return base + compute_check_digit(base)


CLIENT_GSTIN = _gstin("29AAAAA0000A1Z")
SUP_A = _gstin("29BBBBB1234C2Z")


def _login(client, admin) -> str:
    r = client.post(
        "/auth/login",
        json={
            "email": admin["email"],
            "password": admin["password"],
            "totp_code": pyotp.TOTP(admin["totp_secret"]).now(),
        },
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def firm_and_gid(bootstrap_firm):
    admin = bootstrap_firm(admin_email="ws@example.com")
    firm_id = admin["firm_id"]
    cid, gid = uuid.uuid4(), uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO client (id, firm_id, trade_name) VALUES (:c, :f, 'WS')"),
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
    return admin, firm_id, gid


def _insert_invoice(firm_id, gid, *, number, date_, cp, total,
                    hsn="998311", cgst=9_000, sgst=9_000) -> uuid.UUID:
    invoice_id = uuid.uuid4()
    taxable = total - cgst - sgst
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
                    :id, :f, :g, 'csv_import', 'purchase',
                    :num, :dt, :cp,
                    :tx, :cgst, :sgst, 0, :total, :hsn, :h
                )
                """
            ),
            {
                "id": invoice_id, "f": firm_id, "g": gid,
                "num": number, "dt": date_, "cp": cp,
                "tx": taxable, "cgst": cgst, "sgst": sgst,
                "total": total, "hsn": hsn, "h": f"h-{invoice_id}",
            },
        )
    return invoice_id


def _seed_2b(firm_id, gid, *, period, entries):
    pull_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO gstn_pull (id, firm_id, gstin_profile_id, "
                "return_type, period, raw_payload, source) "
                "VALUES (:id, :f, :g, 'GSTR2B', :p, CAST('{}' AS JSONB), "
                "'json_import')"
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


def _audit_rows(firm_id: uuid.UUID, action: str) -> list[dict]:
    with owner_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT action, entity_type, entity_id, diff "
                "FROM audit_log WHERE firm_id = :f AND action = :a "
                "ORDER BY at DESC"
            ),
            {"f": str(firm_id), "a": action},
        ).mappings().all()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Trigger endpoints (sync in P1)
# ---------------------------------------------------------------------------


def test_trigger_validate_then_flags_endpoint(test_client, firm_and_gid) -> None:
    admin, firm_id, gid = firm_and_gid
    _insert_invoice(
        firm_id, gid, number="INV-BAD", date_=date(2026, 6, 15),
        cp=None, total=59_000, cgst=4_500, sgst=4_500, hsn=None,
    )
    access = _login(test_client, admin)
    r = test_client.post(
        "/engines/validate",
        headers={"Authorization": f"Bearer {access}"},
        json={"gstin_profile_id": str(gid), "period": "202606"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["invoices_evaluated"] == 1
    assert body["rule_pack_version"] == "1.0.0"
    # R001 (missing counterparty) fires as an error.
    assert "R001" in body["by_rule"]

    # Audit row landed.
    assert _audit_rows(firm_id, "validation.triggered")

    # /gstins/{id}/flags returns the flag.
    r = test_client.get(
        f"/gstins/{gid}/flags?period=202606",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    flags = r.json()
    assert any(f["rule_code"] == "R001" for f in flags)


def test_full_pipeline_via_api(test_client, firm_and_gid) -> None:
    """End-to-end: validate → reconcile → score → command_center row."""
    admin, firm_id, gid = firm_and_gid
    # Two invoices — one clean, one supplier_default.
    _insert_invoice(
        firm_id, gid, number="M-1", date_=date(2026, 6, 15),
        cp=SUP_A, total=118_000, cgst=9_000, sgst=9_000,
    )
    _insert_invoice(
        firm_id, gid, number="SD-1", date_=date(2026, 6, 20),
        cp=SUP_A, total=59_000, cgst=4_500, sgst=4_500,
    )
    _seed_2b(
        firm_id, gid, period="202606",
        entries=[{"supplier": SUP_A, "number": "M-1",
                  "date": date(2026, 6, 15), "taxable": 100_000,
                  "breakdown": {"cgst": 9_000, "sgst": 9_000, "igst": 0, "cess": 0}}],
    )
    access = _login(test_client, admin)

    for endpoint, payload in [
        ("/engines/validate", {"gstin_profile_id": str(gid), "period": "202606"}),
        ("/engines/reconcile", {"gstin_profile_id": str(gid), "period": "202606"}),
        ("/engines/score", {"gstin_profile_id": str(gid),
                            "return_type": "GSTR1", "period": "202606"}),
    ]:
        r = test_client.post(endpoint, headers={"Authorization": f"Bearer {access}"},
                             json=payload)
        assert r.status_code == 200, f"{endpoint}: {r.text}"

    r = test_client.get(
        f"/gstins/{gid}/reconciliation?period=202606",
        headers={"Authorization": f"Bearer {access}"},
    )
    body = r.json()
    assert body["status"] == "completed"
    assert body["summary"]["matched"]["count"] == 1
    assert body["summary"]["supplier_default"]["count"] == 1

    r = test_client.get(
        f"/gstins/{gid}/readiness?return_type=GSTR1&period=202606",
        headers={"Authorization": f"Bearer {access}"},
    )
    body = r.json()
    assert body["score"] is not None
    assert body["rule_pack_version"] == "1.0.0"
    # blockers array carries paise_impact for supplier_default
    sd = next(b for b in body["blockers"] if b["code"] == "SUPPLIER_DEFAULT_TOTAL")
    assert sd["paise_impact"] == 59_000  # SD-1's total

    # Command center picks the row up.
    r = test_client.get(
        "/command-center?period=202606",
        headers={"Authorization": f"Bearer {access}"},
    )
    rows = r.json()["rows"]
    gstr1 = next(x for x in rows if x["gstin"] == CLIENT_GSTIN and x["return_type"] == "GSTR1")
    assert gstr1["score"] is not None
    assert gstr1["itc_at_risk_paise"] == 59_000


# ---------------------------------------------------------------------------
# Flag resolve → audit_log
# ---------------------------------------------------------------------------


def test_flag_resolve_writes_audit_row(test_client, firm_and_gid) -> None:
    admin, firm_id, gid = firm_and_gid
    _insert_invoice(
        firm_id, gid, number="F-1", date_=date(2026, 6, 15),
        cp=None, total=59_000, cgst=4_500, sgst=4_500, hsn=None,
    )
    access = _login(test_client, admin)
    test_client.post(
        "/engines/validate",
        headers={"Authorization": f"Bearer {access}"},
        json={"gstin_profile_id": str(gid), "period": "202606"},
    )
    flags = test_client.get(
        f"/gstins/{gid}/flags?period=202606",
        headers={"Authorization": f"Bearer {access}"},
    ).json()
    flag = next(f for f in flags if f["rule_code"] == "R001")

    r = test_client.post(
        f"/flags/{flag['id']}/resolve",
        headers={"Authorization": f"Bearer {access}"},
        json={"resolved": True, "note": "confirmed with client"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["resolved"] is True

    # DB state
    with owner_engine.begin() as conn:
        row = conn.execute(
            text("SELECT resolved, resolved_by FROM validation_flag WHERE id = :id"),
            {"id": flag["id"]},
        ).mappings().first()
    assert row["resolved"] is True
    assert row["resolved_by"] is not None

    # Audit row with before/after diff
    rows = _audit_rows(firm_id, "flag.resolved")
    assert len(rows) == 1
    diff = rows[0]["diff"]
    assert diff["before"] == {"resolved": False}
    assert diff["after"]["resolved"] is True
    assert diff["after"]["note"] == "confirmed with client"


# ---------------------------------------------------------------------------
# Match confirm/reject
# ---------------------------------------------------------------------------


def test_confirm_probable_match_promotes_to_matched(
    test_client, firm_and_gid
) -> None:
    admin, firm_id, gid = firm_and_gid
    _insert_invoice(
        firm_id, gid, number="P-1", date_=date(2026, 6, 15),
        cp=SUP_A, total=100_000, cgst=0, sgst=0,
    )
    # 2B entry with slight date + amount diff -> probable
    _seed_2b(
        firm_id, gid, period="202606",
        entries=[{"supplier": SUP_A, "number": "P/1",
                  "date": date(2026, 6, 17), "taxable": 100_200}],
    )
    access = _login(test_client, admin)
    r = test_client.post(
        "/engines/reconcile",
        headers={"Authorization": f"Bearer {access}"},
        json={"gstin_profile_id": str(gid), "period": "202606"},
    )
    run_id = r.json()["run_id"]

    r = test_client.get(
        f"/reconciliation-runs/{run_id}/matches?bucket=probable",
        headers={"Authorization": f"Bearer {access}"},
    )
    matches = r.json()
    assert len(matches) == 1
    match_id = matches[0]["id"]
    assert matches[0]["confidence"] > 0.7

    r = test_client.post(
        f"/match-results/{match_id}/confirm",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200
    assert r.json()["bucket"] == "matched"

    with owner_engine.begin() as conn:
        row = conn.execute(
            text("SELECT bucket::text AS bucket, confirmed_by "
                 "FROM match_result WHERE id = :id"),
            {"id": match_id},
        ).mappings().first()
    assert row["bucket"] == "matched"
    assert row["confirmed_by"] is not None

    assert _audit_rows(firm_id, "match.confirmed")


def test_reject_probable_marks_rejected(test_client, firm_and_gid) -> None:
    admin, firm_id, gid = firm_and_gid
    _insert_invoice(
        firm_id, gid, number="P-2", date_=date(2026, 6, 15),
        cp=SUP_A, total=100_000, cgst=0, sgst=0,
    )
    _seed_2b(
        firm_id, gid, period="202606",
        entries=[{"supplier": SUP_A, "number": "P/2",
                  "date": date(2026, 6, 17), "taxable": 100_200}],
    )
    access = _login(test_client, admin)
    r = test_client.post(
        "/engines/reconcile",
        headers={"Authorization": f"Bearer {access}"},
        json={"gstin_profile_id": str(gid), "period": "202606"},
    )
    run_id = r.json()["run_id"]
    matches = test_client.get(
        f"/reconciliation-runs/{run_id}/matches?bucket=probable",
        headers={"Authorization": f"Bearer {access}"},
    ).json()
    match_id = matches[0]["id"]

    r = test_client.post(
        f"/match-results/{match_id}/reject",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200
    assert r.json()["rejected"] is True
    assert _audit_rows(firm_id, "match.rejected")


def test_confirm_non_probable_rejected(test_client, firm_and_gid) -> None:
    """Confirming an already-matched row is a 400. Only probable can be confirmed."""
    admin, firm_id, gid = firm_and_gid
    _insert_invoice(
        firm_id, gid, number="M-2", date_=date(2026, 6, 15),
        cp=SUP_A, total=100_000, cgst=0, sgst=0,
    )
    _seed_2b(
        firm_id, gid, period="202606",
        entries=[{"supplier": SUP_A, "number": "M-2",
                  "date": date(2026, 6, 15), "taxable": 100_000}],
    )
    access = _login(test_client, admin)
    r = test_client.post(
        "/engines/reconcile",
        headers={"Authorization": f"Bearer {access}"},
        json={"gstin_profile_id": str(gid), "period": "202606"},
    )
    run_id = r.json()["run_id"]
    matches = test_client.get(
        f"/reconciliation-runs/{run_id}/matches?bucket=matched",
        headers={"Authorization": f"Bearer {access}"},
    ).json()
    match_id = matches[0]["id"]
    r = test_client.post(
        f"/match-results/{match_id}/confirm",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# mark-near-miss-reviewed — gates the whatsapp supplier_chase flow
# ---------------------------------------------------------------------------


def _seed_supplier_default_match(firm_id, gid) -> uuid.UUID:
    """Manufacture a supplier_default match_result row so the endpoint
    has a target — sidesteps having to run the full reconciliation to
    reach an unmatched residual."""
    pull_id = uuid.uuid4()
    run_id = uuid.uuid4()
    match_id = uuid.uuid4()
    invoice_id = _insert_invoice(
        firm_id, gid, number="SD-1", date_=date(2026, 6, 15),
        cp=SUP_A, total=100_000, cgst=0, sgst=0,
    )
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO gstn_pull (id, firm_id, gstin_profile_id, "
                "return_type, period, raw_payload, source) "
                "VALUES (:id, :f, :g, 'GSTR2B', '202606', CAST('{}' AS JSONB), "
                "'json_import')"
            ),
            {"id": pull_id, "f": firm_id, "g": gid},
        )
        conn.execute(
            text(
                "INSERT INTO reconciliation_run (id, firm_id, gstin_profile_id, "
                "period, rule_pack_version, gstn_pull_id, summary, status) "
                "VALUES (:id, :f, :g, '202606', '1.0.0', :pid, "
                "CAST('{}' AS JSONB), 'completed')"
            ),
            {"id": run_id, "f": firm_id, "g": gid, "pid": pull_id},
        )
        conn.execute(
            text(
                "INSERT INTO match_result (id, firm_id, run_id, invoice_id, "
                "bucket, confidence, rule_pack_version, context) "
                "VALUES (:id, :f, :rid, :iid, 'supplier_default', 0.0, "
                "'1.0.0', CAST(:ctx AS JSONB))"
            ),
            {
                "id": match_id, "f": firm_id, "rid": run_id,
                "iid": invoice_id,
                "ctx": json.dumps({"near_misses": []}),
            },
        )
    return match_id


def test_mark_near_miss_reviewed_sets_timestamp_preserves_other_keys(
    test_client, firm_and_gid
) -> None:
    admin, firm_id, gid = firm_and_gid
    match_id = _seed_supplier_default_match(firm_id, gid)
    access = _login(test_client, admin)

    r = test_client.post(
        f"/match-results/{match_id}/mark-near-miss-reviewed",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == str(match_id)
    assert body["near_miss_reviewed_at"]

    # DB: near_miss_reviewed_at present, near_misses[] preserved.
    with owner_engine.begin() as conn:
        row = conn.execute(
            text("SELECT context FROM match_result WHERE id = :id"),
            {"id": str(match_id)},
        ).mappings().first()
    assert row["context"]["near_miss_reviewed_at"]
    assert row["context"]["near_misses"] == []

    # Audit trail records the review.
    assert _audit_rows(firm_id, "match.near_miss_reviewed")


def test_mark_near_miss_reviewed_rejects_non_supplier_default(
    test_client, firm_and_gid
) -> None:
    """A probable or matched row must NOT accept a review — the concept
    is meaningless outside supplier_default (there's no near-miss list
    to review on a row that already matched to a 2B entry)."""
    admin, firm_id, gid = firm_and_gid
    _insert_invoice(
        firm_id, gid, number="M-1", date_=date(2026, 6, 15),
        cp=SUP_A, total=100_000, cgst=0, sgst=0,
    )
    _seed_2b(
        firm_id, gid, period="202606",
        entries=[{"supplier": SUP_A, "number": "M-1",
                  "date": date(2026, 6, 15), "taxable": 100_000}],
    )
    access = _login(test_client, admin)
    r = test_client.post(
        "/engines/reconcile",
        headers={"Authorization": f"Bearer {access}"},
        json={"gstin_profile_id": str(gid), "period": "202606"},
    )
    run_id = r.json()["run_id"]
    matches = test_client.get(
        f"/reconciliation-runs/{run_id}/matches?bucket=matched",
        headers={"Authorization": f"Bearer {access}"},
    ).json()
    assert len(matches) == 1
    r = test_client.post(
        f"/match-results/{matches[0]['id']}/mark-near-miss-reviewed",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 400
    assert "supplier_default" in r.json()["detail"]


def test_mark_near_miss_reviewed_is_idempotent_and_each_call_audits(
    test_client, firm_and_gid
) -> None:
    admin, firm_id, gid = firm_and_gid
    match_id = _seed_supplier_default_match(firm_id, gid)
    access = _login(test_client, admin)

    r1 = test_client.post(
        f"/match-results/{match_id}/mark-near-miss-reviewed",
        headers={"Authorization": f"Bearer {access}"},
    )
    first_ts = r1.json()["near_miss_reviewed_at"]

    r2 = test_client.post(
        f"/match-results/{match_id}/mark-near-miss-reviewed",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r2.status_code == 200
    second_ts = r2.json()["near_miss_reviewed_at"]
    # Second call overwrites the timestamp; both audit.
    assert first_ts != second_ts
    audit = _audit_rows(firm_id, "match.near_miss_reviewed")
    assert len(audit) == 2


def test_mark_near_miss_reviewed_unknown_match_is_404(
    test_client, firm_and_gid
) -> None:
    admin, _, _ = firm_and_gid
    access = _login(test_client, admin)
    r = test_client.post(
        f"/match-results/{uuid.uuid4()}/mark-near-miss-reviewed",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 404
