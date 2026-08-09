"""Admin API tests — user list + assignments, with audit_log verification."""
from __future__ import annotations

import uuid

import pyotp
import pytest
from sqlalchemy import text

from app.db import owner_engine
from app.engines.validation.gstin import compute_check_digit


def _gstin(base: str) -> str:
    return base + compute_check_digit(base)


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


def _make_staff(firm_id: uuid.UUID, email: str) -> tuple[uuid.UUID, str, str]:
    from app.auth.passwords import hash_password
    from app.auth.totp import generate_secret
    sid = uuid.uuid4()
    secret = generate_secret()
    pw = "Correct-Horse-Battery-Staple-99"
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app_user (id, firm_id, email, password_hash, "
                "role, totp_secret, totp_confirmed, is_active) "
                "VALUES (:id, :f, :e, :ph, 'staff', :ts, TRUE, TRUE)"
            ),
            {"id": sid, "f": firm_id, "e": email,
             "ph": hash_password(pw), "ts": secret},
        )
    return sid, pw, secret


def test_admin_lists_users_in_firm(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="ad-list@example.com")
    _make_staff(admin["firm_id"], "s1@ex.com")
    access = _login(test_client, admin)
    r = test_client.get("/users", headers={"Authorization": f"Bearer {access}"})
    assert r.status_code == 200, r.text
    rows = r.json()
    emails = {u["email"].lower() for u in rows}
    assert "ad-list@example.com" in emails
    assert "s1@ex.com" in emails
    # last_login_at surfaces on the row (may be null for the seeded
    # staff who hasn't logged in yet, but the field MUST exist).
    for u in rows:
        assert "last_login_at" in u
    admin_row = next(u for u in rows if u["email"].lower() == "ad-list@example.com")
    # The _login helper above just fired — last_login_at is populated.
    assert admin_row["last_login_at"] is not None


def test_staff_cannot_list_users(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="ad-guard@example.com")
    sid, pw, secret = _make_staff(admin["firm_id"], "s2@ex.com")
    r = test_client.post(
        "/auth/login",
        json={"email": "s2@ex.com", "password": pw,
              "totp_code": pyotp.TOTP(secret).now()},
    )
    staff_access = r.json()["access_token"]
    r = test_client.get(
        "/users", headers={"Authorization": f"Bearer {staff_access}"}
    )
    assert r.status_code == 403


def test_assign_and_unassign_writes_audit_rows(
    test_client, bootstrap_firm
) -> None:
    admin = bootstrap_firm(admin_email="ad-assign@example.com")
    sid, _, _ = _make_staff(admin["firm_id"], "s3@ex.com")

    # Create a client via API to prove that path + audit works too.
    access = _login(test_client, admin)
    r = test_client.post(
        "/clients",
        headers={"Authorization": f"Bearer {access}"},
        json={"trade_name": "Client X"},
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    r = test_client.post(
        "/assignments",
        headers={"Authorization": f"Bearer {access}"},
        json={"user_id": str(sid), "client_id": cid},
    )
    assert r.status_code == 201

    r = test_client.delete(
        f"/assignments/{sid}/{cid}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 204

    with owner_engine.begin() as conn:
        actions = [
            a for (a,) in conn.execute(
                text(
                    "SELECT action FROM audit_log WHERE firm_id = :f "
                    "ORDER BY at"
                ),
                {"f": str(admin["firm_id"])},
            ).fetchall()
        ]
    # Three audit rows: client.created, assignment.granted, assignment.revoked.
    assert "client.created" in actions
    assert "assignment.granted" in actions
    assert "assignment.revoked" in actions


def test_client_create_requires_admin(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="ad-x@example.com")
    _, pw, secret = _make_staff(admin["firm_id"], "s4@ex.com")
    r = test_client.post(
        "/auth/login",
        json={"email": "s4@ex.com", "password": pw,
              "totp_code": pyotp.TOTP(secret).now()},
    )
    staff_access = r.json()["access_token"]
    r = test_client.post(
        "/clients",
        headers={"Authorization": f"Bearer {staff_access}"},
        json={"trade_name": "Should Fail"},
    )
    assert r.status_code == 403


def test_add_gstin_and_reject_bad_structure(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="ad-g@example.com")
    access = _login(test_client, admin)
    r = test_client.post(
        "/clients",
        headers={"Authorization": f"Bearer {access}"},
        json={"trade_name": "GC"},
    )
    cid = r.json()["id"]
    r = test_client.post(
        f"/clients/{cid}/gstins",
        headers={"Authorization": f"Bearer {access}"},
        json={"gstin": "NOT-A-GSTIN", "state_code": "29", "scheme": "regular"},
    )
    assert r.status_code == 422

    good_gstin = _gstin("29AAAAA0000A1Z")
    r = test_client.post(
        f"/clients/{cid}/gstins",
        headers={"Authorization": f"Bearer {access}"},
        json={"gstin": good_gstin, "state_code": "29", "scheme": "regular"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["gstin"] == good_gstin
