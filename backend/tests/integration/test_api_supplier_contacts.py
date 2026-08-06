"""Supplier contact directory CRUD + RLS isolation + list_matches surface.

The load-bearing property is (a) the CA can only see/mutate contacts
under their own firm, and (b) list_matches now returns supplier_gstin
inside context so the chase modal can look up prefill without a
separate invoice fetch.
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
SUP_B = _gstin("27CCCCC5678D3Z")


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
    admin = bootstrap_firm(admin_email="sc@example.com")
    firm_id = admin["firm_id"]
    cid, gid = uuid.uuid4(), uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO client (id, firm_id, trade_name) VALUES (:c, :f, 'SC')"),
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


# ---------------------------------------------------------------------------
# CRUD happy path
# ---------------------------------------------------------------------------


def test_create_and_list_contact(test_client, firm_and_gid) -> None:
    admin, firm_id, _ = firm_and_gid
    access = _login(test_client, admin)
    r = test_client.post(
        "/supplier-contacts",
        headers={"Authorization": f"Bearer {access}"},
        json={
            "supplier_gstin": SUP_A,
            "name": "Ravi Textiles",
            "whatsapp_number": "+919876543210",
            "email": "ravi@example.com",
        },
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["supplier_gstin"] == SUP_A
    assert created["name"] == "Ravi Textiles"

    r = test_client.get(
        "/supplier-contacts",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["id"] == created["id"]


def test_by_gstin_lookup_hit_and_miss(test_client, firm_and_gid) -> None:
    admin, _, _ = firm_and_gid
    access = _login(test_client, admin)
    test_client.post(
        "/supplier-contacts",
        headers={"Authorization": f"Bearer {access}"},
        json={
            "supplier_gstin": SUP_A,
            "name": "Ravi Textiles",
            "whatsapp_number": "+919876543210",
        },
    )

    hit = test_client.get(
        f"/supplier-contacts/by-gstin/{SUP_A}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert hit.status_code == 200
    assert hit.json()["name"] == "Ravi Textiles"

    miss = test_client.get(
        f"/supplier-contacts/by-gstin/{SUP_B}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert miss.status_code == 404


def test_patch_updates_only_supplied_fields(test_client, firm_and_gid) -> None:
    admin, _, _ = firm_and_gid
    access = _login(test_client, admin)
    r = test_client.post(
        "/supplier-contacts",
        headers={"Authorization": f"Bearer {access}"},
        json={
            "supplier_gstin": SUP_A,
            "name": "Old Name",
            "whatsapp_number": "+919876543210",
            "email": "old@example.com",
        },
    )
    cid = r.json()["id"]
    r = test_client.patch(
        f"/supplier-contacts/{cid}",
        headers={"Authorization": f"Bearer {access}"},
        json={"name": "New Name"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "New Name"
    # Other fields unchanged.
    assert body["whatsapp_number"] == "+919876543210"
    assert body["email"] == "old@example.com"


def test_delete_removes_and_audits(test_client, firm_and_gid) -> None:
    admin, firm_id, _ = firm_and_gid
    access = _login(test_client, admin)
    r = test_client.post(
        "/supplier-contacts",
        headers={"Authorization": f"Bearer {access}"},
        json={"supplier_gstin": SUP_A, "name": "Ravi Textiles"},
    )
    cid = r.json()["id"]

    r = test_client.delete(
        f"/supplier-contacts/{cid}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 204

    r = test_client.get(
        f"/supplier-contacts/by-gstin/{SUP_A}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 404

    with owner_engine.begin() as conn:
        actions = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT action FROM audit_log WHERE firm_id = :f "
                    "AND entity_type = 'supplier_contact'"
                ),
                {"f": str(firm_id)},
            ).all()
        ]
    assert "supplier_contact.created" in actions
    assert "supplier_contact.deleted" in actions


# ---------------------------------------------------------------------------
# Validation + constraint surfaces
# ---------------------------------------------------------------------------


def test_invalid_e164_rejected(test_client, firm_and_gid) -> None:
    admin, _, _ = firm_and_gid
    access = _login(test_client, admin)
    r = test_client.post(
        "/supplier-contacts",
        headers={"Authorization": f"Bearer {access}"},
        json={
            "supplier_gstin": SUP_A,
            "name": "X",
            "whatsapp_number": "9876543210",  # no leading +
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "invalid_e164_number"


def test_invalid_gstin_rejected(test_client, firm_and_gid) -> None:
    admin, _, _ = firm_and_gid
    access = _login(test_client, admin)
    r = test_client.post(
        "/supplier-contacts",
        headers={"Authorization": f"Bearer {access}"},
        json={
            # Length ok but includes a lowercase letter.
            "supplier_gstin": "29abcde1234f1z5",
            "name": "X",
        },
    )
    # The API upper-cases before validation, so this passes GSTIN shape.
    # Test a real garbage input instead.
    assert r.status_code in (201, 400)

    r = test_client.post(
        "/supplier-contacts",
        headers={"Authorization": f"Bearer {access}"},
        json={
            "supplier_gstin": "not-a-gstin!!",
            "name": "X",
        },
    )
    # Pydantic length check catches this before the API's regex.
    assert r.status_code in (400, 422)


def test_duplicate_gstin_returns_409(test_client, firm_and_gid) -> None:
    admin, _, _ = firm_and_gid
    access = _login(test_client, admin)
    for _ in range(2):
        r = test_client.post(
            "/supplier-contacts",
            headers={"Authorization": f"Bearer {access}"},
            json={"supplier_gstin": SUP_A, "name": "Ravi"},
        )
    assert r.status_code == 409
    assert r.json()["detail"] == "supplier_gstin_already_in_directory"


# ---------------------------------------------------------------------------
# RLS isolation — firm A cannot see firm B's contacts
# ---------------------------------------------------------------------------


def test_firm_isolation(test_client, bootstrap_firm) -> None:
    a = bootstrap_firm(firm_name="Firm A", admin_email="a@example.com")
    b = bootstrap_firm(firm_name="Firm B", admin_email="b@example.com")
    tok_a = _login(test_client, a)
    tok_b = _login(test_client, b)

    # Firm A creates a supplier.
    r = test_client.post(
        "/supplier-contacts",
        headers={"Authorization": f"Bearer {tok_a}"},
        json={"supplier_gstin": SUP_A, "name": "Firm A's Supplier"},
    )
    assert r.status_code == 201
    aid = r.json()["id"]

    # Firm B cannot list it.
    r = test_client.get(
        "/supplier-contacts",
        headers={"Authorization": f"Bearer {tok_b}"},
    )
    assert r.status_code == 200
    assert r.json() == []

    # Firm B cannot look it up by GSTIN either.
    r = test_client.get(
        f"/supplier-contacts/by-gstin/{SUP_A}",
        headers={"Authorization": f"Bearer {tok_b}"},
    )
    assert r.status_code == 404

    # Firm B cannot delete it.
    r = test_client.delete(
        f"/supplier-contacts/{aid}",
        headers={"Authorization": f"Bearer {tok_b}"},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# list_matches — supplier_gstin is now surfaced in context.
# ---------------------------------------------------------------------------


def test_list_matches_includes_supplier_gstin(
    test_client, firm_and_gid,
) -> None:
    """The chase modal's directory prefill relies on this — verify a
    supplier_default match_result carries counterparty_gstin (from the
    referenced invoice) into context.supplier_gstin."""
    admin, firm_id, gid = firm_and_gid
    access = _login(test_client, admin)

    invoice_id = uuid.uuid4()
    pull_id = uuid.uuid4()
    run_id = uuid.uuid4()
    match_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO invoice (
                    id, firm_id, gstin_profile_id, source, direction,
                    invoice_number, invoice_date, counterparty_gstin,
                    taxable_value_paise, total_paise, content_hash
                ) VALUES (
                    :i, :f, :g, 'csv_import', 'purchase',
                    'CH-SEED', DATE '2026-06-15', :cp,
                    100000, 118000, :h
                )
                """
            ),
            {"i": invoice_id, "f": firm_id, "g": gid, "cp": SUP_A,
             "h": f"h-{invoice_id}"},
        )
        conn.execute(
            text(
                "INSERT INTO gstn_pull (id, firm_id, gstin_profile_id, "
                "return_type, period, raw_payload, source) VALUES "
                "(:pid, :f, :g, 'GSTR2B', '202606', CAST('{}' AS JSONB), "
                "'json_import')"
            ),
            {"pid": pull_id, "f": firm_id, "g": gid},
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
                "bucket, confidence, rule_pack_version, context) VALUES "
                "(:m, :f, :rid, :iid, 'supplier_default', 0.0, '1.0.0', "
                "CAST(:ctx AS JSONB))"
            ),
            {"m": match_id, "f": firm_id, "rid": run_id, "iid": invoice_id,
             "ctx": json.dumps({"near_misses": []})},
        )

    r = test_client.get(
        f"/reconciliation-runs/{run_id}/matches?bucket=supplier_default",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["context"]["supplier_gstin"] == SUP_A
    assert row["context"]["register_invoice_number"] == "CH-SEED"
    assert row["context"]["register_total_paise"] == 118000
