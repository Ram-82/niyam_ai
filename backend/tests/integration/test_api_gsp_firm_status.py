"""GET /gsp/firm-status — aggregate GSP connection status across the firm.

Onboarding step 3 hangs off `any_connected`. This suite proves the
aggregate matches the per-GSTIN endpoint's individual states."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pyotp
from sqlalchemy import text

from app.db import owner_engine
from app.engines.validation.gstin import compute_check_digit


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


def _mk_gstin(base14: str) -> str:
    return base14 + compute_check_digit(base14)


def _add_client_with_gstin(firm_id, gstin: str, state_code: str) -> uuid.UUID:
    client_id = uuid.uuid4()
    gid = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name, language) "
                "VALUES (:id, :fid, :n, 'en')"
            ),
            {"id": client_id, "fid": firm_id, "n": f"Client for {gstin}"},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code, scheme) "
                "VALUES (:id, :fid, :cid, :g, :sc, 'regular'::gst_scheme)"
            ),
            {"id": gid, "fid": firm_id, "cid": client_id, "g": gstin, "sc": state_code},
        )
    return gid


def _firm_of(gstin_profile_id: uuid.UUID) -> uuid.UUID:
    with owner_engine.begin() as conn:
        row = conn.execute(
            text("SELECT firm_id FROM gstin_profile WHERE id = :id"),
            {"id": gstin_profile_id},
        ).first()
    assert row is not None
    return row[0]


def _add_live_session(gstin_profile_id: uuid.UUID) -> None:
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO gsp_session (firm_id, gstin_profile_id, token_ciphertext, key_version, "
                "vendor_context, issued_at, expires_at) "
                "VALUES (:fid, :g, :tok, 1, '{}'::jsonb, :ia, :exp)"
            ),
            {
                "fid": _firm_of(gstin_profile_id),
                "g": gstin_profile_id,
                "tok": b"stub-ciphertext",
                "ia": datetime.now(timezone.utc),
                "exp": datetime.now(timezone.utc) + timedelta(hours=6),
            },
        )


def _add_revoked_session(gstin_profile_id: uuid.UUID, reason: str) -> None:
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO gsp_session (firm_id, gstin_profile_id, token_ciphertext, key_version, "
                "vendor_context, issued_at, expires_at, revoked_at, revoked_reason) "
                "VALUES (:fid, :g, :tok, 1, '{}'::jsonb, :ia, :exp, :rev, :reason)"
            ),
            {
                "fid": _firm_of(gstin_profile_id),
                "g": gstin_profile_id,
                "tok": b"stub-ciphertext",
                "ia": datetime.now(timezone.utc) - timedelta(hours=2),
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),
                "rev": datetime.now(timezone.utc) - timedelta(minutes=30),
                "reason": reason,
            },
        )


def test_no_gstins_returns_zeros_with_label(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"g0-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)
    r = test_client.get("/gsp/firm-status", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {
        "total_gstins": 0,
        "connected": 0,
        "reconnect_needed": 0,
        "not_connected": 0,
        "any_connected": False,
        "summary_label": "No GSTINs added yet",
    }


def test_mixed_states_aggregated_correctly(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"g1-{uuid.uuid4().hex[:6]}@example.com")
    firm_id = admin["firm_id"]

    live_gid = _add_client_with_gstin(firm_id, _mk_gstin("29AAAAA0000A1Z"), "29")
    _add_live_session(live_gid)

    revoked_gid = _add_client_with_gstin(firm_id, _mk_gstin("27BBBBB0000B1Z"), "27")
    _add_revoked_session(revoked_gid, "session_expired")

    _add_client_with_gstin(firm_id, _mk_gstin("24CCCCC0000C1Z"), "24")

    tok = _bearer(test_client, admin)
    r = test_client.get("/gsp/firm-status", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_gstins"] == 3
    assert body["connected"] == 1
    assert body["reconnect_needed"] == 1
    assert body["not_connected"] == 1
    assert body["any_connected"] is True
    assert "1 connected" in body["summary_label"]
    assert "1 need reconnect" in body["summary_label"]


def test_all_connected_shows_all_label(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"g2-{uuid.uuid4().hex[:6]}@example.com")
    firm_id = admin["firm_id"]
    g1 = _add_client_with_gstin(firm_id, _mk_gstin("29DDDDD0000D1Z"), "29")
    g2 = _add_client_with_gstin(firm_id, _mk_gstin("27EEEEE0000E1Z"), "27")
    _add_live_session(g1)
    _add_live_session(g2)
    tok = _bearer(test_client, admin)
    r = test_client.get("/gsp/firm-status", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    body = r.json()
    assert body["connected"] == 2
    assert body["any_connected"] is True
    assert body["summary_label"] == "All 2 GSTINs connected"
