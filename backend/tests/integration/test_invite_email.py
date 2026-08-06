"""POST /invites/ email dispatch — enabled and disabled paths."""
from __future__ import annotations

import pyotp
import pytest

from app.email import MemoryTransport, reset_transport_for_tests


STRONG_PW = "Correct-Horse-Battery-Staple-42"


def _admin_token(client, admin) -> str:
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
def memory_email():
    mem = MemoryTransport()
    reset_transport_for_tests(mem)
    yield mem
    reset_transport_for_tests(None)


def test_invite_sends_email_when_enabled(
    test_client, bootstrap_firm, monkeypatch, memory_email
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "email_app_base_url", "https://app.example.test")

    admin = bootstrap_firm(firm_name="Acme CA LLP", admin_email="admin@example.com")
    access = _admin_token(test_client, admin)

    r = test_client.post(
        "/invites/",
        json={"email": "newbie@example.com", "role": "staff"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 201, r.text
    invite_token = r.json()["invite_token"]

    assert len(memory_email.sent) == 1
    msg = memory_email.sent[0]
    assert msg.to == "newbie@example.com"
    assert "Acme CA LLP" in msg.subject
    # Body carries the raw token so the invitee can accept.
    assert invite_token in msg.body_text
    # Absolute URL built from settings.email_app_base_url.
    assert "https://app.example.test/register?token=" in msg.body_text


def test_invite_skips_email_when_disabled(
    test_client, bootstrap_firm, monkeypatch, memory_email
) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "email_enabled", False)

    admin = bootstrap_firm(admin_email="silent-admin@example.com")
    access = _admin_token(test_client, admin)

    r = test_client.post(
        "/invites/",
        json={"email": "quiet@example.com", "role": "staff"},
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 201, r.text
    # Invite is still created (token in response) — but nothing dispatched.
    assert r.json()["invite_token"]
    assert memory_email.sent == []


def test_transport_failure_does_not_break_invite(
    test_client, bootstrap_firm, monkeypatch
) -> None:
    """If the email transport blows up, the invite MUST still be created
    and returned — the copy-URL UI is the contract-guaranteed fallback."""
    from app.config import settings

    class _BoomTransport:
        def send(self, msg):
            raise RuntimeError("smtp down")

    reset_transport_for_tests(_BoomTransport())
    try:
        monkeypatch.setattr(settings, "email_enabled", True)
        admin = bootstrap_firm(admin_email="boom-admin@example.com")
        access = _admin_token(test_client, admin)

        r = test_client.post(
            "/invites/",
            json={"email": "recipient@example.com", "role": "staff"},
            headers={"Authorization": f"Bearer {access}"},
        )
        assert r.status_code == 201, r.text
        # Raw token still returned — admin can copy the link manually.
        assert r.json()["invite_token"]
    finally:
        reset_transport_for_tests(None)
