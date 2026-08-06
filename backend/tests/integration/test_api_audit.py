"""/audit-log read + write coverage.

Property under test:
- filings/generate + regenerate write audit rows with the right actions.
- /auth/login success writes an ``auth.login`` row.
- /invites POST writes ``invite.created``.
- /audit-log endpoint returns rows scoped to firm, honours filters,
  and does NOT leak firm A's rows to firm B.
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


# ---------------------------------------------------------------------------
# Auth login audits
# ---------------------------------------------------------------------------


def test_login_success_writes_audit_row(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="al@example.com")
    access = _login(test_client, admin)
    r = test_client.get(
        "/audit-log?action_prefix=auth.login",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    rows = r.json()
    assert any(row["action"] == "auth.login" for row in rows), rows


# ---------------------------------------------------------------------------
# Filings audits
# ---------------------------------------------------------------------------


def test_filings_generate_and_regenerate_write_distinct_actions(
    test_client, bootstrap_firm
) -> None:
    admin, _, gid = _seed_firm_with_sale("fga@example.com", bootstrap_firm)
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
    assert r1.status_code == 200
    r2 = test_client.post(
        "/filings/generate",
        headers={"Authorization": f"Bearer {access}"},
        json=body,
    )
    assert r2.status_code == 200

    r = test_client.get(
        "/audit-log?entity_type=filing_run",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    actions = [row["action"] for row in r.json()]
    assert "filing.generated" in actions
    assert "filing.regenerated" in actions


# ---------------------------------------------------------------------------
# Invites audits
# ---------------------------------------------------------------------------


def test_invite_create_writes_invite_created(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="ia@example.com")
    access = _login(test_client, admin)
    r = test_client.post(
        "/invites/",
        headers={"Authorization": f"Bearer {access}"},
        json={"email": "new@example.com", "role": "staff"},
    )
    assert r.status_code == 201, r.text
    invite_id = r.json()["invite_id"]

    audit = test_client.get(
        f"/audit-log?entity_type=user_invite&entity_id={invite_id}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert audit.status_code == 200
    rows = audit.json()
    assert any(row["action"] == "invite.created" for row in rows), rows


# ---------------------------------------------------------------------------
# RLS isolation on /audit-log
# ---------------------------------------------------------------------------


def test_audit_log_rls_no_cross_firm_leak(test_client, bootstrap_firm) -> None:
    admin_a, _, gid_a = _seed_firm_with_sale("ra@example.com", bootstrap_firm)
    admin_b = bootstrap_firm(admin_email="rb@example.com")

    access_a = _login(test_client, admin_a)
    access_b = _login(test_client, admin_b)

    # A generates a filing -> writes an audit row
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

    # B reads /audit-log with the filing_run entity_type filter
    r = test_client.get(
        "/audit-log?entity_type=filing_run",
        headers={"Authorization": f"Bearer {access_b}"},
    )
    assert r.status_code == 200
    # B must not see A's filing.generated
    for row in r.json():
        assert row["action"] != "filing.generated" or row["user_email"] == admin_b["email"]
    # Sanity: A CAN see it
    r = test_client.get(
        "/audit-log?entity_type=filing_run",
        headers={"Authorization": f"Bearer {access_a}"},
    )
    assert r.status_code == 200
    assert any(row["action"] == "filing.generated" for row in r.json())
