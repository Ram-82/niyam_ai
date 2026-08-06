"""POST /invites/{id}/resend — token rotation + re-dispatch."""
from __future__ import annotations

import pyotp
import pytest

from app.config import settings
from app.email import MemoryTransport, reset_transport_for_tests


@pytest.fixture
def memory_email(monkeypatch):
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "email_app_base_url", "https://app.example.test")
    mem = MemoryTransport()
    reset_transport_for_tests(mem)
    yield mem
    reset_transport_for_tests(None)


def _bearer(client, admin) -> str:
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


def test_resend_rotates_token_and_reemails(
    test_client, bootstrap_firm, memory_email
) -> None:
    admin = bootstrap_firm(admin_email="resend-admin@example.com")
    tok = _bearer(test_client, admin)

    # 1. Create original invite.
    r = test_client.post(
        "/invites/",
        json={"email": "new@example.com", "role": "staff"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 201, r.text
    orig = r.json()
    orig_token = orig["invite_token"]
    orig_expiry = orig["expires_at"]
    assert len(memory_email.sent) == 1

    memory_email.clear()

    # 2. Resend.
    r = test_client.post(
        f"/invites/{orig['invite_id']}/resend",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    fresh = r.json()
    assert fresh["invite_id"] == orig["invite_id"]
    assert fresh["invite_token"] != orig_token
    # Expiry moved forward (fresh 72h window).
    assert fresh["expires_at"] > orig_expiry
    assert len(memory_email.sent) == 1
    assert fresh["invite_token"] in memory_email.sent[0].body_text

    # 3. Old token no longer registers.
    r = test_client.post(
        "/auth/register",
        json={"invite_token": orig_token, "password": "Correct-Horse-Battery-Staple-42"},
    )
    assert r.status_code == 400

    # 4. New token registers successfully.
    r = test_client.post(
        "/auth/register",
        json={"invite_token": fresh["invite_token"], "password": "Correct-Horse-Battery-Staple-42"},
    )
    assert r.status_code == 201, r.text


def test_resend_rejected_for_accepted_invite(
    test_client, bootstrap_firm, memory_email
) -> None:
    admin = bootstrap_firm(admin_email="already-accepted-admin@example.com")
    tok = _bearer(test_client, admin)

    r = test_client.post(
        "/invites/",
        json={"email": "consumer@example.com", "role": "staff"},
        headers={"Authorization": f"Bearer {tok}"},
    )
    invite = r.json()

    # Accept it.
    r = test_client.post(
        "/auth/register",
        json={"invite_token": invite["invite_token"], "password": "Correct-Horse-Battery-Staple-42"},
    )
    assert r.status_code == 201, r.text

    # Resend must now 409.
    r = test_client.post(
        f"/invites/{invite['invite_id']}/resend",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 409, r.text


def test_resend_unknown_id_returns_404(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="unknown-invite-admin@example.com")
    tok = _bearer(test_client, admin)
    r = test_client.post(
        "/invites/00000000-0000-0000-0000-000000000000/resend",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 404


def test_resend_requires_admin_role(test_client, bootstrap_firm, memory_email) -> None:
    """Staff role must not be able to resend invites."""
    from app.db import owner_engine
    from sqlalchemy import text as _text
    from app.auth.passwords import hash_password
    from app.auth.totp import generate_secret
    import uuid

    admin = bootstrap_firm(admin_email="orig-admin@example.com")
    tok_admin = _bearer(test_client, admin)

    # Create an invite as admin.
    r = test_client.post(
        "/invites/",
        json={"email": "future-staff@example.com", "role": "staff"},
        headers={"Authorization": f"Bearer {tok_admin}"},
    )
    invite = r.json()

    # Seed a staff user directly (not from the invite — we want the
    # role check to fire before the invite state matters).
    staff_id = uuid.uuid4()
    staff_secret = generate_secret()
    with owner_engine.begin() as conn:
        conn.execute(
            _text(
                """
                INSERT INTO app_user (
                    id, firm_id, email, password_hash, role,
                    totp_secret, totp_confirmed, is_active
                ) VALUES (
                    :id, :fid, 'a-staff@example.com', :ph, 'staff',
                    :ts, TRUE, TRUE
                )
                """
            ),
            {
                "id": staff_id, "fid": admin["firm_id"],
                "ph": hash_password("Correct-Horse-Battery-Staple-42"),
                "ts": staff_secret,
            },
        )

    r = test_client.post(
        "/auth/login",
        json={
            "email": "a-staff@example.com",
            "password": "Correct-Horse-Battery-Staple-42",
            "totp_code": pyotp.TOTP(staff_secret).now(),
        },
    )
    staff_tok = r.json()["access_token"]

    r = test_client.post(
        f"/invites/{invite['invite_id']}/resend",
        headers={"Authorization": f"Bearer {staff_tok}"},
    )
    assert r.status_code == 403, r.text
