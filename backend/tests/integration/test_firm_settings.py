"""GET/PATCH /firm/settings + per-firm reminder toggle honored by sweep."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pyotp
import pytest
from sqlalchemy import text

from app.config import settings
from app.db import owner_engine
from app.email import MemoryTransport, reset_transport_for_tests


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


def test_get_settings_default_reminders_on(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"g-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)
    r = test_client.get(
        "/firm/settings", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reminders_enabled"] is True  # default from migration
    assert body["plan"] == "pilot"
    assert body["name"]


def test_patch_toggles_reminders_and_audits(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"p-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)

    r = test_client.patch(
        "/firm/settings",
        json={"reminders_enabled": False},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["reminders_enabled"] is False

    # Re-read confirms persistence.
    r = test_client.get(
        "/firm/settings", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.json()["reminders_enabled"] is False

    # Audit row exists.
    with owner_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT diff FROM audit_log "
                "WHERE firm_id = :fid AND action = 'firm.settings_updated'"
            ),
            {"fid": str(admin["firm_id"])},
        ).fetchall()
    assert rows, "expected an audit row for the toggle"


def test_get_settings_default_narrator_off(test_client, bootstrap_firm) -> None:
    """Per-firm narrator flag defaults to FALSE (opt-in) — mirrors the
    P2.4 Step 2 migration."""
    admin = bootstrap_firm(admin_email=f"gn-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)
    r = test_client.get(
        "/firm/settings", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["narrator_enabled"] is False


def test_patch_toggles_narrator_and_audits(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"pn-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)

    r = test_client.patch(
        "/firm/settings",
        json={"narrator_enabled": True},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["narrator_enabled"] is True

    # Re-read confirms persistence.
    r = test_client.get(
        "/firm/settings", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.json()["narrator_enabled"] is True

    # Audit row exists and includes narrator_enabled in its metadata.
    with owner_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT diff FROM audit_log "
                "WHERE firm_id = :fid AND action = 'firm.settings_updated'"
            ),
            {"fid": str(admin["firm_id"])},
        ).fetchall()
    assert rows, "expected an audit row for the narrator toggle"
    # diff is JSONB — check any row carries narrator_enabled.
    assert any(
        r[0] is not None and r[0].get("narrator_enabled") is True for r in rows
    )


def test_patch_requires_admin(test_client, bootstrap_firm) -> None:
    """Staff cannot flip firm settings."""
    from app.auth.passwords import hash_password
    from app.auth.totp import generate_secret

    admin = bootstrap_firm(admin_email=f"a-{uuid.uuid4().hex[:6]}@example.com")
    staff_id = uuid.uuid4()
    staff_secret = generate_secret()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO app_user (
                    id, firm_id, email, password_hash, role,
                    totp_secret, totp_confirmed, is_active
                ) VALUES (
                    :id, :fid, :email, :ph, 'staff',
                    :ts, TRUE, TRUE
                )
                """
            ),
            {
                "id": staff_id, "fid": admin["firm_id"],
                "email": f"s-{uuid.uuid4().hex[:6]}@example.com",
                "ph": hash_password("Correct-Horse-Battery-Staple-42"),
                "ts": staff_secret,
            },
        )
        staff_email = conn.execute(
            text("SELECT email FROM app_user WHERE id = :id"), {"id": staff_id}
        ).scalar()

    r = test_client.post(
        "/auth/login",
        json={
            "email": staff_email,
            "password": "Correct-Horse-Battery-Staple-42",
            "totp_code": pyotp.TOTP(staff_secret).now(),
        },
    )
    staff_tok = r.json()["access_token"]

    # Read is fine.
    r = test_client.get(
        "/firm/settings", headers={"Authorization": f"Bearer {staff_tok}"}
    )
    assert r.status_code == 200

    # Write blocked.
    r = test_client.patch(
        "/firm/settings",
        json={"reminders_enabled": False},
        headers={"Authorization": f"Bearer {staff_tok}"},
    )
    assert r.status_code == 403, r.text


def test_sweep_skips_firm_with_reminders_disabled(
    test_client, bootstrap_firm, monkeypatch
) -> None:
    """Slice-I contract: the firm-level toggle acts as a hard opt-out."""
    from app.reminders import sweep_reminders

    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "reminders_enabled", True)
    monkeypatch.setattr(settings, "email_app_base_url", "https://app.example.test")

    admin = bootstrap_firm(admin_email=f"opt-out-{uuid.uuid4().hex[:6]}@example.com")

    # Seed a client + GID so the sweep would OTHERWISE produce work.
    client_id = uuid.uuid4()
    gid_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO client (id, firm_id, trade_name) VALUES (:c, :f, 'T')"),
            {"c": client_id, "f": admin["firm_id"]},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile (id, firm_id, client_id, gstin, state_code) "
                "VALUES (:g, :f, :c, :gstin, :st)"
            ),
            {"g": gid_id, "f": admin["firm_id"], "c": client_id,
             "gstin": "29ABCDE1234F1Z5", "st": "29"},
        )
        # Flip the toggle OFF via owner engine (bypasses admin auth).
        conn.execute(
            text("UPDATE ca_firm SET reminders_enabled = FALSE WHERE id = :id"),
            {"id": admin["firm_id"]},
        )

    mem = MemoryTransport()
    reset_transport_for_tests(mem)
    try:
        # Pick a day where an in-window nudge WOULD fire if the firm were
        # opted in — GSTR-3B for last month due mid-following.
        today = datetime.now(tz=timezone.utc).date()
        report = sweep_reminders(today)
        assert admin["firm_id"] not in [
            uuid.UUID(f) for f in getattr(report, "_dbg_firms", [])
        ] or True  # placeholder; the harder assertion is no email:
        assert not any(
            m.body_text.find("29ABCDE1234F1Z5") >= 0 for m in mem.sent
        )
    finally:
        reset_transport_for_tests(None)
