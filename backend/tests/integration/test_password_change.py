"""POST /auth/password/change — authenticated self-service password change."""
from __future__ import annotations

import time

import pyotp
import pytest
from sqlalchemy import text

from app.db import owner_engine


STRONG_PW = "Correct-Horse-Battery-Staple-42"
FRESH_PW = "Zebra-Fanfare-9-Puzzle-Onyx"


def _login(client, admin) -> dict:
    r = client.post(
        "/auth/login",
        json={
            "email": admin["email"],
            "password": admin["password"],
            "totp_code": pyotp.TOTP(admin["totp_secret"]).now(),
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_change_password_happy_path(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="changer@example.com")
    tokens = _login(test_client, admin)

    r = test_client.post(
        "/auth/password/change",
        json={"current_password": STRONG_PW, "new_password": FRESH_PW},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 204, r.text

    # Old password no longer works.
    r = test_client.post(
        "/auth/login",
        json={
            "email": admin["email"],
            "password": STRONG_PW,
            "totp_code": pyotp.TOTP(admin["totp_secret"]).now(),
        },
    )
    assert r.status_code == 401

    # New password does.
    r = test_client.post(
        "/auth/login",
        json={
            "email": admin["email"],
            "password": FRESH_PW,
            "totp_code": pyotp.TOTP(admin["totp_secret"]).now(),
        },
    )
    assert r.status_code == 200, r.text


def test_wrong_current_password_rejected(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="wrong-current@example.com")
    tokens = _login(test_client, admin)
    r = test_client.post(
        "/auth/password/change",
        json={"current_password": "definitely-not-the-password", "new_password": FRESH_PW},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 401, r.text


def test_weak_new_password_rejected(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="weak-new@example.com")
    tokens = _login(test_client, admin)
    r = test_client.post(
        "/auth/password/change",
        json={"current_password": STRONG_PW, "new_password": "short"},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 400, r.text


def test_unauthenticated_change_rejected(test_client) -> None:
    r = test_client.post(
        "/auth/password/change",
        json={"current_password": STRONG_PW, "new_password": FRESH_PW},
    )
    # No bearer → 401 (or 403 depending on dependency style). Never 204.
    assert r.status_code in (401, 403), r.text


def test_other_refresh_tokens_invalidated_on_change(
    test_client, bootstrap_firm
) -> None:
    """A refresh token from a prior session must fail after a change —
    same guarantee as the reset flow, powered by the same iat gate."""
    admin = bootstrap_firm(admin_email="kick-on-change@example.com")

    # 1. Log in twice — imagine two devices. Grab the "other" refresh.
    old = _login(test_client, admin)
    old_refresh = old["refresh_token"]

    # 2. Wait so password_changed_at lands strictly after the token iat.
    time.sleep(1.1)

    # 3. Change password using the CURRENT session's access token.
    current = _login(test_client, admin)
    r = test_client.post(
        "/auth/password/change",
        json={"current_password": STRONG_PW, "new_password": FRESH_PW},
        headers={"Authorization": f"Bearer {current['access_token']}"},
    )
    assert r.status_code == 204, r.text

    # 4. The OLD refresh token now fails.
    r = test_client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 401


def test_audit_row_written_on_change(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="audit-change@example.com")
    tokens = _login(test_client, admin)
    r = test_client.post(
        "/auth/password/change",
        json={"current_password": STRONG_PW, "new_password": FRESH_PW},
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
    )
    assert r.status_code == 204

    with owner_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT action FROM audit_log "
                "WHERE firm_id = :fid AND action = 'auth.password_changed'"
            ),
            {"fid": str(admin["firm_id"])},
        ).fetchall()
    assert rows, "expected an auth.password_changed audit row"
