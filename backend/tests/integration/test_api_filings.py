"""/filings API — happy path + RLS isolation.

Property under test: firm-B cannot read/regenerate firm-A's filing_run,
and generating twice updates in place (unique on gid+period+return_type).
"""
from __future__ import annotations

import uuid

import pyotp
import pytest
from sqlalchemy import text

from app.db import owner_engine
from app.engines.validation.gstin import compute_check_digit


CLIENT_GSTIN = "29AAAAA0000A1Z" + compute_check_digit("29AAAAA0000A1Z")
BUYER = "27BBBBB1234C2Z" + compute_check_digit("27BBBBB1234C2Z")


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


def _seed_firm_with_sale(admin_email: str, bootstrap_firm) -> tuple:
    admin = bootstrap_firm(admin_email=admin_email)
    firm_id = admin["firm_id"]
    cid, gid = uuid.uuid4(), uuid.uuid4()
    with owner_engine.begin() as c:
        c.execute(
            text("INSERT INTO client (id, firm_id, trade_name) VALUES (:c, :f, 'X')"),
            {"c": cid, "f": firm_id},
        )
        c.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code, scheme) "
                "VALUES (:g, :f, :c, :gs, '29', 'regular')"
            ),
            {"g": gid, "f": firm_id, "c": cid, "gs": CLIENT_GSTIN},
        )
        c.execute(
            text(
                """
                INSERT INTO invoice (
                    firm_id, gstin_profile_id, source, direction,
                    invoice_number, invoice_date, counterparty_gstin,
                    taxable_value_paise, cgst_paise, sgst_paise, igst_paise,
                    total_paise, content_hash
                ) VALUES (
                    :f, :g, 'csv_import', 'sale',
                    'S-1', DATE '2026-07-15', :cp,
                    100000, 0, 0, 12000, 112000, 'h-S-1'
                )
                """
            ),
            {"f": firm_id, "g": gid, "cp": BUYER},
        )
    return admin, firm_id, gid


def test_generate_gstr1_happy_path(test_client, bootstrap_firm) -> None:
    admin, _, gid = _seed_firm_with_sale("fa@example.com", bootstrap_firm)
    access = _login(test_client, admin)
    r = test_client.post(
        "/filings/generate",
        headers={"Authorization": f"Bearer {access}"},
        json={
            "gstin_profile_id": str(gid),
            "period": "202607",
            "return_type": "GSTR1",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["return_type"] == "GSTR1"
    assert body["period"] == "202607"
    assert body["status"] == "draft"
    assert body["payload"]["fp"] == "072026"
    assert body["payload"]["b2b"][0]["ctin"] == BUYER


def test_regenerate_updates_in_place(test_client, bootstrap_firm) -> None:
    admin, _, gid = _seed_firm_with_sale("fb@example.com", bootstrap_firm)
    access = _login(test_client, admin)
    body = {
        "gstin_profile_id": str(gid),
        "period": "202607",
        "return_type": "GSTR1",
    }
    r1 = test_client.post(
        "/filings/generate",
        headers={"Authorization": f"Bearer {access}"},
        json=body,
    )
    assert r1.status_code == 200, r1.text
    r2 = test_client.post(
        "/filings/generate",
        headers={"Authorization": f"Bearer {access}"},
        json=body,
    )
    assert r2.status_code == 200, r2.text
    # Same id — regenerate overwrote, did not append
    assert r1.json()["id"] == r2.json()["id"]


def test_rls_firm_b_cannot_see_firm_a_filing(
    test_client, bootstrap_firm
) -> None:
    admin_a, _, gid_a = _seed_firm_with_sale("ra@example.com", bootstrap_firm)
    admin_b, _, _ = _seed_firm_with_sale("rb@example.com", bootstrap_firm)
    access_a = _login(test_client, admin_a)
    access_b = _login(test_client, admin_b)

    # A creates a filing
    r = test_client.post(
        "/filings/generate",
        headers={"Authorization": f"Bearer {access_a}"},
        json={
            "gstin_profile_id": str(gid_a),
            "period": "202607",
            "return_type": "GSTR1",
        },
    )
    assert r.status_code == 200
    filing_id = r.json()["id"]

    # B tries to read it — must be 404 (RLS hides the row)
    r = test_client.get(
        f"/filings/{filing_id}",
        headers={"Authorization": f"Bearer {access_b}"},
    )
    assert r.status_code == 404
