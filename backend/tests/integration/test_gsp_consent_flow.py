"""Stage 2 integration tests — consent flow, encryption at rest, RLS,
OTP secrecy, lockout, audit trail.

These map 1:1 to the Stage 2 entry criteria:

    (1) gsp_session + gsp_call_log follow P1 tenancy:
        firm_id, FORCE RLS, cross-firm isolation.
    (2) encryption proven at the row level: raw DB row is ciphertext;
        round-trip only via app layer; key from env; rotation seam
        documented + tested (see tests/unit/test_gsp_crypto.py).
    (3) OTPs never persisted or logged.
    (4) initiate/confirm rate-limited per (user, gstin);
        lockouts audited.
    (5) connect / reconnect / disconnect audited with actor.

The mock GSP server runs in-process on port 9099 via a background
uvicorn thread; the MockGSPAdapter talks HTTP to it. Same wire path as
the real docker service — no bypass.
"""
from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from contextlib import closing
from typing import Iterator

import pytest
import uvicorn
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError, ProgrammingError

from app.db import app_engine, owner_engine
from app.gsp import crypto, lockout, service
from app.gsp.mock_server import FIXED_OTP, app as mock_app


# ---------------------------------------------------------------------------
# In-process mock server fixture
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def mock_gsp_server() -> Iterator[str]:
    """Boot the mock GSP server on a free port in a background thread."""
    port = _free_port()
    config = uvicorn.Config(
        mock_app, host="127.0.0.1", port=port, log_level="warning"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # Wait for readiness — try /health up to 5s.
    import httpx

    base = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if httpx.get(f"{base}/health", timeout=0.5).status_code == 200:
                break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError("mock GSP server never became ready")
    yield base
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def _point_service_at_mock(mock_gsp_server, monkeypatch):
    """Force ``service.get_adapter`` to use the running mock server."""
    from app.gsp import adapter_mock, service as svc

    def _factory():
        return adapter_mock.MockGSPAdapter(base_url=mock_gsp_server)

    monkeypatch.setattr(svc, "get_adapter", _factory)
    # Also reset in-flight consent cache between tests
    svc._inflight.clear()
    from app.gsp import mock_server as m

    m._sessions.clear()
    m._consent_requests.clear()


# ---------------------------------------------------------------------------
# Firm / GSTIN seed helpers
# ---------------------------------------------------------------------------


CLIENT_GSTIN = "29ZZZZZ9999Z9Z9"


@pytest.fixture
def firm_with_gstin() -> dict:
    firm_id = uuid.uuid4()
    user_id = uuid.uuid4()
    client_id = uuid.uuid4()
    gstin_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ca_firm (id, name) VALUES (:id, 'Test Firm')"),
            {"id": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO app_user (id, firm_id, email, password_hash, role, "
                "totp_confirmed, is_active) "
                "VALUES (:id, :fid, 'a@x.com', 'x', 'admin', TRUE, TRUE)"
            ),
            {"id": user_id, "fid": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:cid, :fid, 'Acme')"
            ),
            {"cid": client_id, "fid": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code) "
                "VALUES (:gid, :fid, :cid, :g, '29')"
            ),
            {"gid": gstin_id, "fid": firm_id, "cid": client_id, "g": CLIENT_GSTIN},
        )
    return {
        "firm_id": firm_id,
        "user_id": user_id,
        "client_id": client_id,
        "gstin_profile_id": gstin_id,
        "gstin": CLIENT_GSTIN,
    }


def _pin(conn, firm_id):
    conn.execute(
        text("SELECT set_config('app.current_firm_id', :f, true)"),
        {"f": str(firm_id)},
    )


# ---------------------------------------------------------------------------
# (5) Full happy path — connect → session persisted → audit + consent_log
# ---------------------------------------------------------------------------


def test_connect_flow_persists_encrypted_session_and_writes_audit(firm_with_gstin) -> None:
    ff = firm_with_gstin
    initiated = service.initiate_consent(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        user_id=ff["user_id"],
    )
    service.confirm_consent(
        firm_id=ff["firm_id"],
        user_id=ff["user_id"],
        inflight_id=initiated.inflight_id,
        otp=FIXED_OTP,
    )
    # gsp_session row exists (owner engine bypasses RLS for assertion).
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT firm_id, gstin_profile_id, token_ciphertext, "
                "key_version, connected_by, revoked_at "
                "FROM gsp_session WHERE gstin_profile_id = :gpid"
            ),
            {"gpid": str(ff["gstin_profile_id"])},
        ).mappings().one()
    assert row["firm_id"] == ff["firm_id"]
    assert row["revoked_at"] is None
    assert row["connected_by"] == ff["user_id"]
    assert row["key_version"] == crypto.current_key_version()
    # audit_log has a connect row keyed to the actor.
    with owner_engine.begin() as conn:
        audit = conn.execute(
            text(
                "SELECT action, user_id, entity_type FROM audit_log "
                "WHERE firm_id = :f ORDER BY at DESC"
            ),
            {"f": str(ff["firm_id"])},
        ).all()
    actions = [r[0] for r in audit]
    assert "gsp.connect" in actions
    connect_row = next(r for r in audit if r[0] == "gsp.connect")
    assert connect_row[1] == ff["user_id"]
    assert connect_row[2] == "gstin_profile"
    # consent_log has a grant row.
    with owner_engine.begin() as conn:
        cl = conn.execute(
            text(
                "SELECT purpose, granted_by, metadata FROM consent_log "
                "WHERE firm_id = :f ORDER BY granted_at DESC"
            ),
            {"f": str(ff["firm_id"])},
        ).mappings().all()
    assert cl and cl[0]["purpose"] == "gsp.gstr2b"
    assert cl[0]["granted_by"] == ff["user_id"]
    assert cl[0]["metadata"]["action"] == "connect"


def test_reconnect_supersedes_old_row_and_audits_reconnect(firm_with_gstin) -> None:
    ff = firm_with_gstin
    # First connect.
    r1 = service.initiate_consent(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        user_id=ff["user_id"],
    )
    service.confirm_consent(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        inflight_id=r1.inflight_id, otp=FIXED_OTP,
    )
    # Second connect (reconnect).
    r2 = service.initiate_consent(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        user_id=ff["user_id"],
    )
    service.confirm_consent(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        inflight_id=r2.inflight_id, otp=FIXED_OTP,
    )
    with owner_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT revoked_at, revoked_reason FROM gsp_session "
                "WHERE gstin_profile_id = :gpid ORDER BY connected_at"
            ),
            {"gpid": str(ff["gstin_profile_id"])},
        ).all()
    assert len(rows) == 2
    assert rows[0][0] is not None  # old row revoked
    assert rows[0][1] == "reconnect"
    assert rows[1][0] is None  # new row live
    with owner_engine.begin() as conn:
        actions = [
            r[0] for r in conn.execute(
                text("SELECT action FROM audit_log WHERE firm_id = :f"),
                {"f": str(ff["firm_id"])},
            ).all()
        ]
    assert actions.count("gsp.connect") == 1
    assert actions.count("gsp.reconnect") == 1


def test_disconnect_marks_session_revoked_and_audits(firm_with_gstin) -> None:
    ff = firm_with_gstin
    r = service.initiate_consent(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        user_id=ff["user_id"],
    )
    service.confirm_consent(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        inflight_id=r.inflight_id, otp=FIXED_OTP,
    )
    service.disconnect(
        firm_id=ff["firm_id"],
        user_id=ff["user_id"],
        gstin_profile_id=ff["gstin_profile_id"],
    )
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT revoked_at, revoked_reason FROM gsp_session "
                "WHERE gstin_profile_id = :gpid"
            ),
            {"gpid": str(ff["gstin_profile_id"])},
        ).one()
    assert row[0] is not None
    assert row[1] == "user_disconnected"
    with owner_engine.begin() as conn:
        actions = [
            r[0] for r in conn.execute(
                text("SELECT action FROM audit_log WHERE firm_id = :f"),
                {"f": str(ff["firm_id"])},
            ).all()
        ]
    assert "gsp.disconnect" in actions
    # Consent log carries a revoke row with granted_by=actor.
    with owner_engine.begin() as conn:
        cl = conn.execute(
            text(
                "SELECT metadata, granted_by, revoked_at FROM consent_log "
                "WHERE firm_id = :f AND metadata->>'action' = 'disconnect'"
            ),
            {"f": str(ff["firm_id"])},
        ).mappings().one()
    assert cl["revoked_at"] is not None
    assert cl["granted_by"] == ff["user_id"]


# ---------------------------------------------------------------------------
# (2) Encryption proven at the row level
# ---------------------------------------------------------------------------


def test_row_level_ciphertext_never_contains_plaintext_token(firm_with_gstin) -> None:
    ff = firm_with_gstin
    r = service.initiate_consent(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        user_id=ff["user_id"],
    )
    service.confirm_consent(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        inflight_id=r.inflight_id, otp=FIXED_OTP,
    )
    # The mock server keeps sessions by token — pluck the plaintext from
    # its state to assert absence in the DB row.
    from app.gsp import mock_server as m

    (plaintext_token,) = list(m._sessions.keys())
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT token_ciphertext, key_version "
                "FROM gsp_session WHERE gstin_profile_id = :gpid"
            ),
            {"gpid": str(ff["gstin_profile_id"])},
        ).one()
    ct, kv = row
    assert isinstance(ct, (bytes, memoryview))
    ct = bytes(ct)
    # Ciphertext must not contain the plaintext token as a substring.
    assert plaintext_token.encode("ascii") not in ct
    # Round-trip only via app layer.
    assert crypto.decrypt(ct, kv) == plaintext_token


# ---------------------------------------------------------------------------
# (3) OTPs never persisted or logged
# ---------------------------------------------------------------------------


def test_otp_absent_from_all_persisted_artifacts(firm_with_gstin) -> None:
    ff = firm_with_gstin
    # Do one successful confirm and one failed confirm so both paths run.
    r = service.initiate_consent(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        user_id=ff["user_id"],
    )
    from app.gsp.client import OTPInvalid

    with pytest.raises(OTPInvalid):
        service.confirm_consent(
            firm_id=ff["firm_id"], user_id=ff["user_id"],
            inflight_id=r.inflight_id, otp="000000",
        )
    service.confirm_consent(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        inflight_id=r.inflight_id, otp=FIXED_OTP,
    )
    # Search every persisted artifact for the OTP substring.
    otps = {FIXED_OTP.encode(), b"000000"}
    with owner_engine.begin() as conn:
        for table, cols in [
            ("audit_log", "COALESCE(diff::text,'')"),
            ("consent_log", "COALESCE(metadata::text,'')"),
            ("gsp_call_log", "COALESCE(endpoint,'') || COALESCE(error_kind,'')"),
            ("gsp_session", "COALESCE(vendor_context::text,'')"),
        ]:
            for r in conn.execute(text(f"SELECT {cols} FROM {table}")).all():
                blob = r[0].encode() if isinstance(r[0], str) else bytes(r[0])
                for otp in otps:
                    assert otp not in blob, (
                        f"OTP leaked into {table}: {blob!r}"
                    )


# ---------------------------------------------------------------------------
# (4) Rate-limit per (user, gstin) + audited lockout transition
# ---------------------------------------------------------------------------


def test_five_wrong_otps_locks_out_and_audits(firm_with_gstin) -> None:
    ff = firm_with_gstin
    r = service.initiate_consent(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        user_id=ff["user_id"],
    )
    from app.gsp.client import OTPInvalid

    for _ in range(lockout.MAX_ATTEMPTS):
        with pytest.raises(OTPInvalid):
            service.confirm_consent(
                firm_id=ff["firm_id"], user_id=ff["user_id"],
                inflight_id=r.inflight_id, otp="000000",
            )
    # Sixth attempt: locked out (raises OtpLockedOut before hitting adapter).
    with pytest.raises(service.OtpLockedOut) as exc_info:
        service.confirm_consent(
            firm_id=ff["firm_id"], user_id=ff["user_id"],
            inflight_id=r.inflight_id, otp=FIXED_OTP,
        )
    assert exc_info.value.retry_after > 0
    # audit_log has exactly one gsp.otp_lockout row (transition audited once).
    with owner_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT user_id, entity_id, diff FROM audit_log "
                "WHERE firm_id = :f AND action = 'gsp.otp_lockout'"
            ),
            {"f": str(ff["firm_id"])},
        ).mappings().all()
    assert len(rows) == 1
    assert rows[0]["user_id"] == ff["user_id"]
    assert rows[0]["entity_id"] == ff["gstin_profile_id"]
    # OTP not in the audit metadata.
    md = rows[0]["diff"]
    assert FIXED_OTP not in json.dumps(md)
    assert "000000" not in json.dumps(md)


def test_lockout_is_scoped_to_user_and_gstin(firm_with_gstin) -> None:
    """Lockout on (userA, gstinX) must not lock (userA, gstinY) or (userB, gstinX)."""
    ff = firm_with_gstin
    # Second GSTIN for the same client.
    other_gid = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code) "
                "VALUES (:gid, :fid, :cid, '27BBBBB1111B2Z6', '27')"
            ),
            {"gid": other_gid, "fid": ff["firm_id"], "cid": ff["client_id"]},
        )
    r = service.initiate_consent(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        user_id=ff["user_id"],
    )
    from app.gsp.client import OTPInvalid

    for _ in range(lockout.MAX_ATTEMPTS):
        with pytest.raises(OTPInvalid):
            service.confirm_consent(
                firm_id=ff["firm_id"], user_id=ff["user_id"],
                inflight_id=r.inflight_id, otp="000000",
            )
    # Now consent on the OTHER gstin from same user — must proceed
    # (not locked because lockout is (user, gstin) scoped).
    r2 = service.initiate_consent(
        firm_id=ff["firm_id"], gstin_profile_id=other_gid, user_id=ff["user_id"],
    )
    service.confirm_consent(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        inflight_id=r2.inflight_id, otp=FIXED_OTP,
    )


# ---------------------------------------------------------------------------
# (1) Cross-firm isolation
# ---------------------------------------------------------------------------


@pytest.mark.rls
def test_cross_firm_rls_isolation_on_gsp_session(firm_with_gstin) -> None:
    ff = firm_with_gstin
    r = service.initiate_consent(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        user_id=ff["user_id"],
    )
    service.confirm_consent(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        inflight_id=r.inflight_id, otp=FIXED_OTP,
    )
    # A different firm pinned via the app engine must see zero rows.
    other_firm = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ca_firm (id, name) VALUES (:id, 'Other')"),
            {"id": other_firm},
        )
    with app_engine.begin() as conn:
        _pin(conn, other_firm)
        rows = conn.execute(text("SELECT id FROM gsp_session")).all()
    assert rows == []
    with app_engine.begin() as conn:
        _pin(conn, other_firm)
        rows = conn.execute(text("SELECT id FROM gsp_call_log")).all()
    assert rows == []


@pytest.mark.rls
def test_gsp_call_log_insert_wrong_firm_id_blocked(firm_with_gstin) -> None:
    ff = firm_with_gstin
    other_firm = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ca_firm (id, name) VALUES (:id, 'Other')"),
            {"id": other_firm},
        )
    with pytest.raises((DatabaseError, ProgrammingError)):
        with app_engine.begin() as conn:
            _pin(conn, ff["firm_id"])
            conn.execute(
                text(
                    "INSERT INTO gsp_call_log "
                    "(firm_id, endpoint, succeeded, latency_ms) "
                    "VALUES (:f, 'consent', TRUE, 1)"
                ),
                {"f": str(other_firm)},
            )


@pytest.mark.rls
def test_gsp_call_log_is_append_only(firm_with_gstin) -> None:
    """Even the owner-role UPDATE/DELETE is blocked by the mutation
    trigger — belt-and-braces even without RLS."""
    ff = firm_with_gstin
    # Seed one row via the service.
    r = service.initiate_consent(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        user_id=ff["user_id"],
    )
    del r
    with pytest.raises((DatabaseError, ProgrammingError)):
        with owner_engine.begin() as conn:
            conn.execute(text("UPDATE gsp_call_log SET succeeded = FALSE"))
    with pytest.raises((DatabaseError, ProgrammingError)):
        with owner_engine.begin() as conn:
            conn.execute(text("DELETE FROM gsp_call_log"))


# ---------------------------------------------------------------------------
# CONSENT_REVOKED / SESSION_EXPIRED mid-lifecycle
# ---------------------------------------------------------------------------


def test_mark_session_dead_consent_revoked_writes_consent_log(firm_with_gstin) -> None:
    ff = firm_with_gstin
    r = service.initiate_consent(
        firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
        user_id=ff["user_id"],
    )
    service.confirm_consent(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        inflight_id=r.inflight_id, otp=FIXED_OTP,
    )
    service.mark_session_dead(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        reason="consent_revoked",
    )
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT revoked_at, revoked_reason FROM gsp_session "
                "WHERE gstin_profile_id = :g"
            ),
            {"g": str(ff["gstin_profile_id"])},
        ).one()
    assert row[0] is not None
    assert row[1] == "consent_revoked"
    with owner_engine.begin() as conn:
        actions = [
            r[0] for r in conn.execute(
                text(
                    "SELECT action FROM audit_log WHERE firm_id = :f "
                    "ORDER BY at DESC"
                ),
                {"f": str(ff["firm_id"])},
            ).all()
        ]
        # Consent log entry: revoked_by_vendor with actor NULL.
        cl = conn.execute(
            text(
                "SELECT granted_by, revoked_at, metadata FROM consent_log "
                "WHERE firm_id = :f AND metadata->>'action' = 'revoked_by_vendor'"
            ),
            {"f": str(ff["firm_id"])},
        ).mappings().one()
    assert "gsp.consent_revoked" in actions
    assert cl["granted_by"] is None  # system actor, no human
    assert cl["revoked_at"] is not None


def test_mark_session_dead_session_expired_no_consent_log(firm_with_gstin) -> None:
    """SESSION_EXPIRED is not a consent event; only audit_log records it."""
    ff = firm_with_gstin
    r = service.initiate_consent(
        firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
        user_id=ff["user_id"],
    )
    service.confirm_consent(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        inflight_id=r.inflight_id, otp=FIXED_OTP,
    )
    service.mark_session_dead(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        reason="session_expired",
    )
    with owner_engine.begin() as conn:
        actions = [
            r[0] for r in conn.execute(
                text("SELECT action FROM audit_log WHERE firm_id = :f"),
                {"f": str(ff["firm_id"])},
            ).all()
        ]
        cl_actions = [
            r[0] for r in conn.execute(
                text(
                    "SELECT metadata->>'action' FROM consent_log "
                    "WHERE firm_id = :f"
                ),
                {"f": str(ff["firm_id"])},
            ).all()
        ]
    assert "gsp.session_expired" in actions
    assert "revoked_by_vendor" not in cl_actions


# ---------------------------------------------------------------------------
# load_live_session (Stage 3 preview) — round-trip
# ---------------------------------------------------------------------------


def test_load_live_session_returns_decrypted_token(firm_with_gstin) -> None:
    ff = firm_with_gstin
    r = service.initiate_consent(
        firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
        user_id=ff["user_id"],
    )
    service.confirm_consent(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        inflight_id=r.inflight_id, otp=FIXED_OTP,
    )
    live = service.load_live_session(
        firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"]
    )
    assert live is not None
    from app.gsp import mock_server as m
    (plaintext_token,) = list(m._sessions.keys())
    assert live.session.token == plaintext_token
    assert live.session.gstin == CLIENT_GSTIN


def test_load_live_session_returns_none_when_revoked(firm_with_gstin) -> None:
    ff = firm_with_gstin
    r = service.initiate_consent(
        firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
        user_id=ff["user_id"],
    )
    service.confirm_consent(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        inflight_id=r.inflight_id, otp=FIXED_OTP,
    )
    service.disconnect(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        gstin_profile_id=ff["gstin_profile_id"],
    )
    assert service.load_live_session(
        firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"]
    ) is None
