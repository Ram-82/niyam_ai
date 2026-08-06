"""/auth/login + /auth/register 429 shape."""
from __future__ import annotations

import pyotp

from app.auth import rate_limit


def test_login_returns_429_after_ip_burst(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="rl-ip@example.com")
    body = {
        "email": admin["email"],
        "password": admin["password"],
        "totp_code": pyotp.TOTP(admin["totp_secret"]).now(),
    }
    # First N requests within the window are allowed (some may 401 due to
    # rapid-fire TOTP replay — that's fine, we're only checking 429 shape).
    n = rate_limit.POLICIES["login_ip"].max_hits
    for _ in range(n):
        test_client.post("/auth/login", json=body)
    # The next one MUST be 429 regardless of credentials.
    r = test_client.post("/auth/login", json=body)
    assert r.status_code == 429, r.text
    assert r.headers.get("Retry-After"), "429 must carry a Retry-After header"


def test_login_email_bucket_scopes_per_email(test_client, bootstrap_firm) -> None:
    # A separate email from a shared IP MUST hit the email limit sooner
    # than the IP limit (max_hits=5 vs 10). Exhaust the email bucket for
    # user A; user B on the same IP still works.
    a = bootstrap_firm(admin_email="a-rl@example.com")
    b = bootstrap_firm(admin_email="b-rl@example.com")

    a_body = {
        "email": a["email"], "password": a["password"],
        "totp_code": pyotp.TOTP(a["totp_secret"]).now(),
    }
    b_body = {
        "email": b["email"], "password": b["password"],
        "totp_code": pyotp.TOTP(b["totp_secret"]).now(),
    }

    n = rate_limit.POLICIES["login_email"].max_hits
    for _ in range(n):
        test_client.post("/auth/login", json=a_body)
    r_a = test_client.post("/auth/login", json=a_body)
    assert r_a.status_code == 429

    # B still allowed (email bucket is fresh).
    r_b = test_client.post("/auth/login", json=b_body)
    assert r_b.status_code != 429, r_b.text


def test_register_ip_limit(test_client) -> None:
    # invite_token must satisfy Field(min_length=8) or Pydantic 422s
    # before the endpoint body runs — and the rate-limit call lives in
    # the endpoint. Use a syntactically valid but semantically-bogus
    # token so the request reaches the limiter.
    body = {"invite_token": "not-a-real-token-1234", "password": "irrelevant"}
    n = rate_limit.POLICIES["register_ip"].max_hits
    for _ in range(n):
        r = test_client.post("/auth/register", json=body)
        # Should be 400 (InvalidInviteError) — but NOT 422 (bad shape)
        # and NOT 429 (limit not yet hit).
        assert r.status_code == 400, r.text
    r = test_client.post("/auth/register", json=body)
    assert r.status_code == 429
    assert r.headers.get("Retry-After")
