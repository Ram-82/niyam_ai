"""/auth/password/forgot + /auth/password/reset — end-to-end flow."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from sqlalchemy import text

from app.auth import password_reset, rate_limit
from app.db import owner_engine
from app.email import MemoryTransport, reset_transport_for_tests


STRONG_PW = "Correct-Horse-Battery-Staple-42"
FRESH_PW = "Zebra-Fanfare-9-Puzzle-Onyx"


def _extract_token(mem: MemoryTransport) -> str:
    """Pull the reset token out of the emailed body."""
    assert len(mem.sent) == 1, f"expected 1 email, got {len(mem.sent)}"
    body = mem.sent[0].body_text
    marker = "/reset-password?token="
    idx = body.find(marker)
    assert idx >= 0, f"no reset link in body: {body!r}"
    tail = body[idx + len(marker):]
    return tail.split()[0].strip()


@pytest.fixture
def memory_email(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "email_app_base_url", "https://app.example.test")
    mem = MemoryTransport()
    reset_transport_for_tests(mem)
    yield mem
    reset_transport_for_tests(None)


@pytest.fixture(autouse=True)
def _clear_rl():
    # Password reset uses tight per-hour limits; a burst across tests
    # in the same worker would false-fire otherwise.
    rate_limit._redis.eval(
        "for _, k in ipairs(redis.call('keys', ARGV[1])) do redis.call('del', k) end; return 0",
        0,
        "rl:forgot_*",
    )
    yield


def test_full_reset_flow_replaces_password(
    test_client, bootstrap_firm, memory_email
) -> None:
    admin = bootstrap_firm(admin_email="reset-me@example.com")

    # 1. Forgot request → 202 + email dispatched.
    r = test_client.post("/auth/password/forgot", json={"email": admin["email"]})
    assert r.status_code == 202, r.text
    token = _extract_token(memory_email)

    # 2. Reset with the token → 204.
    r = test_client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": FRESH_PW},
    )
    assert r.status_code == 204, r.text

    # 3. Old password rejected.
    r = test_client.post(
        "/auth/login",
        json={
            "email": admin["email"],
            "password": STRONG_PW,
            "totp_code": pyotp.TOTP(admin["totp_secret"]).now(),
        },
    )
    assert r.status_code == 401

    # 4. New password works.
    r = test_client.post(
        "/auth/login",
        json={
            "email": admin["email"],
            "password": FRESH_PW,
            "totp_code": pyotp.TOTP(admin["totp_secret"]).now(),
        },
    )
    assert r.status_code == 200, r.text


def test_unknown_email_returns_202_without_sending(
    test_client, memory_email
) -> None:
    r = test_client.post(
        "/auth/password/forgot",
        json={"email": "no-such-user-here@example.com"},
    )
    # Enumeration-safety contract: same 202 as the happy path.
    assert r.status_code == 202, r.text
    assert memory_email.sent == []


def test_reused_token_rejected(
    test_client, bootstrap_firm, memory_email
) -> None:
    admin = bootstrap_firm(admin_email="reuse@example.com")
    r = test_client.post("/auth/password/forgot", json={"email": admin["email"]})
    assert r.status_code == 202
    token = _extract_token(memory_email)

    # First use succeeds.
    r = test_client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": FRESH_PW},
    )
    assert r.status_code == 204

    # Second use rejected — single-shot.
    r = test_client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": "Another-Fresh-Pw-777x"},
    )
    assert r.status_code == 400
    assert "used" in r.text.lower()


def test_expired_token_rejected(
    test_client, bootstrap_firm, memory_email, monkeypatch
) -> None:
    # Force TTL to 0s so the token issued below is expired before the reset call.
    monkeypatch.setattr(password_reset, "RESET_TOKEN_TTL_SECONDS", 0)
    admin = bootstrap_firm(admin_email="expiry@example.com")

    r = test_client.post("/auth/password/forgot", json={"email": admin["email"]})
    assert r.status_code == 202
    token = _extract_token(memory_email)

    # Tiny wait so now > expires_at (which was created at ~now).
    time.sleep(0.05)
    r = test_client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": FRESH_PW},
    )
    assert r.status_code == 400
    assert "expired" in r.text.lower()


def test_unknown_token_rejected(test_client) -> None:
    r = test_client.post(
        "/auth/password/reset",
        json={"token": "definitely-not-a-real-token-1234567890", "new_password": FRESH_PW},
    )
    assert r.status_code == 400


def test_weak_password_rejected(
    test_client, bootstrap_firm, memory_email
) -> None:
    admin = bootstrap_firm(admin_email="weak@example.com")
    r = test_client.post("/auth/password/forgot", json={"email": admin["email"]})
    assert r.status_code == 202
    token = _extract_token(memory_email)

    r = test_client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": "short"},
    )
    assert r.status_code == 400


def test_refresh_after_reset_is_invalidated(
    test_client, bootstrap_firm, memory_email
) -> None:
    """A refresh token issued before the reset must fail — otherwise a
    compromised session survives the reset."""
    admin = bootstrap_firm(admin_email="kick-sessions@example.com")

    # 1. Log in and grab a refresh token.
    r = test_client.post(
        "/auth/login",
        json={
            "email": admin["email"],
            "password": STRONG_PW,
            "totp_code": pyotp.TOTP(admin["totp_secret"]).now(),
        },
    )
    assert r.status_code == 200, r.text
    old_refresh = r.json()["refresh_token"]

    # 2. Sleep 1s — password_changed_at needs to land strictly after iat
    # of the just-issued refresh token (both in unix seconds).
    time.sleep(1.1)

    # 3. Reset.
    r = test_client.post("/auth/password/forgot", json={"email": admin["email"]})
    assert r.status_code == 202
    token = _extract_token(memory_email)
    r = test_client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": FRESH_PW},
    )
    assert r.status_code == 204

    # 4. Old refresh token rejected — iat < password_changed_at.
    r = test_client.post("/auth/refresh", json={"refresh_token": old_refresh})
    assert r.status_code == 401


def test_forgot_email_rate_limit(
    test_client, bootstrap_firm, memory_email
) -> None:
    admin = bootstrap_firm(admin_email="rl-forgot@example.com")
    n = rate_limit.POLICIES["forgot_email"].max_hits
    for _ in range(n):
        r = test_client.post("/auth/password/forgot", json={"email": admin["email"]})
        assert r.status_code == 202
    # Next hit on the same email → 429 regardless of validity.
    r = test_client.post("/auth/password/forgot", json={"email": admin["email"]})
    assert r.status_code == 429
    assert r.headers.get("Retry-After")


def test_audit_row_written_on_successful_reset(
    test_client, bootstrap_firm, memory_email
) -> None:
    admin = bootstrap_firm(admin_email="audit-reset@example.com")
    r = test_client.post("/auth/password/forgot", json={"email": admin["email"]})
    token = _extract_token(memory_email)
    r = test_client.post(
        "/auth/password/reset",
        json={"token": token, "new_password": FRESH_PW},
    )
    assert r.status_code == 204

    with owner_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT action FROM audit_log "
                "WHERE firm_id = :fid AND action = 'auth.password_reset'"
            ),
            {"fid": str(admin["firm_id"])},
        ).fetchall()
    assert rows, "expected an auth.password_reset audit row"
