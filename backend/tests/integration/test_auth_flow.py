"""End-to-end auth flow tests against a live Postgres + Redis.

These tests exercise the FastAPI app via TestClient. They use the
``bootstrap_firm`` fixture to seed the first admin (invite chicken-and-egg),
then drive the invite -> register -> login -> totp -> /me -> refresh path.
"""
from __future__ import annotations

import time
import uuid
from typing import Any

import pyotp
import pytest
from sqlalchemy import text

from app.auth import lockout, rate_limit
from app.db import owner_engine


STRONG_PW = "Correct-Horse-Battery-Staple-42"
ALT_PW = "Slightly-Different-Passphrase-99"


def _login_admin(client, email: str, password: str, totp_secret: str) -> dict[str, Any]:
    code = pyotp.TOTP(totp_secret).now()
    r = client.post(
        "/auth/login",
        json={"email": email, "password": password, "totp_code": code},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_invite_register_login_totp_end_to_end(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="admin1@example.com")

    # 1. Admin logs in with password + TOTP.
    tokens = _login_admin(
        test_client, admin["email"], admin["password"], admin["totp_secret"]
    )
    access = tokens["access_token"]

    # 2. Admin creates an invite for a staff user.
    r = test_client.post(
        "/invites/",
        json={"email": "newbie@example.com", "role": "staff"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 201, r.text
    invite = r.json()
    invite_token = invite["invite_token"]

    # 3. Invitee registers.
    r = test_client.post(
        "/auth/register",
        json={"invite_token": invite_token, "password": ALT_PW},
    )
    assert r.status_code == 201, r.text
    reg = r.json()
    assert reg["next"] == "totp_setup"
    assert uuid.UUID(reg["firm_id"]) == admin["firm_id"]

    # 4. Invitee logs in — returns a totp_setup token (no access yet).
    r = test_client.post(
        "/auth/login",
        json={"email": "newbie@example.com", "password": ALT_PW},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    setup_token = body["totp_setup_token"]
    assert "access_token" not in body

    # 5. Kick off TOTP setup.
    r = test_client.post(
        "/auth/totp/setup",
        headers={"Authorization": f"Bearer {setup_token}"},
    )
    assert r.status_code == 200, r.text
    setup_payload = r.json()
    assert setup_payload["provisioning_uri"].startswith("otpauth://totp/")
    newbie_secret = setup_payload["secret"]

    # 6. Verify TOTP -> real access + refresh.
    code = pyotp.TOTP(newbie_secret).now()
    r = test_client.post(
        "/auth/totp/verify",
        json={"code": code},
        headers={"Authorization": f"Bearer {setup_token}"},
    )
    assert r.status_code == 200, r.text
    pair = r.json()
    newbie_access = pair["access_token"]
    newbie_refresh = pair["refresh_token"]

    # 7. /me returns the invitee scoped to the admin's firm.
    r = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {newbie_access}"},
    )
    assert r.status_code == 200, r.text
    me = r.json()
    assert me["email"].lower() == "newbie@example.com"
    assert uuid.UUID(me["firm_id"]) == admin["firm_id"]
    assert me["role"] == "staff"
    assert me["totp_confirmed"] is True

    # 8. Refresh rotates.
    r = test_client.post("/auth/refresh", json={"refresh_token": newbie_refresh})
    assert r.status_code == 200, r.text
    new_pair = r.json()
    assert new_pair["refresh_token"] != newbie_refresh


def test_login_wrong_password_locks_after_five(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="lockme@example.com")
    for i in range(lockout.MAX_ATTEMPTS):
        r = test_client.post(
            "/auth/login",
            json={"email": admin["email"], "password": "wrong-pw-xxxx-xxxx"},
        )
        assert r.status_code == 401, f"attempt {i}: {r.text}"

    # 6th attempt: now locked.
    r = test_client.post(
        "/auth/login",
        json={"email": admin["email"], "password": "wrong-pw-xxxx-xxxx"},
    )
    assert r.status_code == 429, r.text
    assert "Retry-After" in r.headers

    # Audit row should have been written on the lockout transition. Query
    # via owner engine (bypasses RLS) since we don't have a session token.
    with owner_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT action FROM audit_log "
                "WHERE firm_id = :fid AND action = 'auth.lockout'"
            ),
            {"fid": str(admin["firm_id"])},
        ).fetchall()
    assert rows, "expected an auth.lockout audit row"


def test_lockout_expires_after_window(test_client, bootstrap_firm, monkeypatch) -> None:
    admin = bootstrap_firm(admin_email="shortlock@example.com")
    # Shrink the lockout window so the test finishes in reasonable time.
    monkeypatch.setattr(lockout, "WINDOW_SECONDS", 2)
    for _ in range(lockout.MAX_ATTEMPTS):
        test_client.post(
            "/auth/login",
            json={"email": admin["email"], "password": "wrong-pw-xxxx-xxxx"},
        )
    assert lockout.is_locked(admin["email"])
    time.sleep(2.5)
    assert not lockout.is_locked(admin["email"])
    # The failed-login burst above also consumed this email's rate-limit
    # bucket. Lockout and rate-limit are two independent throttles; this
    # test targets lockout, so drop the rate-limit counters explicitly
    # before proving the correct password now works.
    rate_limit.reset("login_email", admin["email"])
    rate_limit.reset("login_ip", "testclient")
    # Correct login now succeeds again.
    r = test_client.post(
        "/auth/login",
        json={
            "email": admin["email"],
            "password": admin["password"],
            "totp_code": pyotp.TOTP(admin["totp_secret"]).now(),
        },
    )
    assert r.status_code == 200, r.text


def test_refresh_rotation_revokes_old(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="rotate@example.com")
    tokens = _login_admin(
        test_client, admin["email"], admin["password"], admin["totp_secret"]
    )
    old_refresh = tokens["refresh_token"]

    # First refresh works.
    r = test_client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 200, r.text

    # Same refresh again should now fail (rotation revoked it).
    r = test_client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 401, r.text


def test_access_to_me_requires_totp_confirmed(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="preadmin@example.com")
    tokens = _login_admin(
        test_client, admin["email"], admin["password"], admin["totp_secret"]
    )
    access = tokens["access_token"]

    # Create invite + register a new user; they have totp_confirmed=false.
    r = test_client.post(
        "/invites/",
        json={"email": "pre-totp@example.com", "role": "staff"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 201, r.text
    invite_token = r.json()["invite_token"]
    r = test_client.post(
        "/auth/register",
        json={"invite_token": invite_token, "password": ALT_PW},
    )
    assert r.status_code == 201, r.text

    # Their login returns a totp_setup token, not an access token.
    r = test_client.post(
        "/auth/login",
        json={"email": "pre-totp@example.com", "password": ALT_PW},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    setup_token = body["totp_setup_token"]

    # /me with the totp_setup token is rejected (typ != access).
    r = test_client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {setup_token}"},
    )
    assert r.status_code == 403, r.text


def test_cross_firm_admin_cannot_list_other_firm_invites(
    test_client, bootstrap_firm
) -> None:
    admin_a = bootstrap_firm(firm_name="Firm A", admin_email="a-admin@example.com")
    admin_b = bootstrap_firm(firm_name="Firm B", admin_email="b-admin@example.com")

    tokens_a = _login_admin(
        test_client, admin_a["email"], admin_a["password"], admin_a["totp_secret"]
    )
    tokens_b = _login_admin(
        test_client, admin_b["email"], admin_b["password"], admin_b["totp_secret"]
    )

    # Firm B admin creates an invite.
    r = test_client.post(
        "/invites/",
        json={"email": "b-staff@example.com", "role": "staff"},
        headers={"Authorization": f"Bearer {tokens_b['access_token']}"},
    )
    assert r.status_code == 201, r.text

    # Firm A admin lists invites — should NOT see firm B's invite.
    r = test_client.get(
        "/invites/",
        headers={"Authorization": f"Bearer {tokens_a['access_token']}"},
    )
    assert r.status_code == 200, r.text
    emails = [row["email"].lower() for row in r.json()]
    assert "b-staff@example.com" not in emails
