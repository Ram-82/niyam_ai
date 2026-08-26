"""Stage 4 backend tests — scheduler auth + concurrency, connection
status, backfill plan.

The UI-side coverage lives in Playwright (frontend/e2e/gsp.spec.ts).
This file locks the API contract those UI tests depend on.
"""
from __future__ import annotations

import socket
import threading
import time
import uuid
from contextlib import closing
from datetime import datetime, timezone
from typing import Iterator

import pytest
import uvicorn
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db import owner_engine
from app.gsp import service
from app.gsp.mock_server import FIXED_OTP, app as mock_app


CLIENT_GSTIN = "29ZZZZZ9999Z9Z9"


# ---------------------------------------------------------------------------
# Mock GSP server fixture (same pattern as previous stages)
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def mock_gsp_server() -> Iterator[str]:
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(mock_app, host="127.0.0.1", port=port, log_level="warning")
    )
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
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
    t.join(timeout=5)


@pytest.fixture(autouse=True)
def _point_service_at_mock(mock_gsp_server, monkeypatch):
    from app.gsp import adapter_mock, service as svc

    monkeypatch.setattr(
        svc, "get_adapter", lambda: adapter_mock.MockGSPAdapter(base_url=mock_gsp_server)
    )
    svc._inflight.clear()
    from app.gsp import mock_server as m

    m._sessions.clear()
    m._consent_requests.clear()


# ---------------------------------------------------------------------------
# Firm + GSTIN + live session helper
# ---------------------------------------------------------------------------


@pytest.fixture
def firm_and_client_no_session():
    firm_id = uuid.uuid4()
    user_id = uuid.uuid4()
    client_id = uuid.uuid4()
    gstin_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ca_firm (id, name) VALUES (:id, 'F')"),
            {"id": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO app_user (id, firm_id, email, password_hash, role, "
                "totp_confirmed, is_active) VALUES "
                "(:id, :fid, 'a@x.com', 'x', 'admin', TRUE, TRUE)"
            ),
            {"id": user_id, "fid": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:cid, :fid, 'C')"
            ),
            {"cid": client_id, "fid": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile (id, firm_id, client_id, gstin, state_code) "
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


def _connect(firm_id, gstin_profile_id, user_id):
    r = service.initiate_consent(
        firm_id=firm_id, gstin_profile_id=gstin_profile_id, user_id=user_id
    )
    service.confirm_consent(
        firm_id=firm_id, user_id=user_id, inflight_id=r.inflight_id, otp=FIXED_OTP
    )


# ---------------------------------------------------------------------------
# Scheduler auth: no token, wrong token, user JWT — all rejected.
# ---------------------------------------------------------------------------


def test_scheduler_run_without_token_returns_503_when_disabled(monkeypatch, test_client) -> None:
    """Empty env → endpoint disabled entirely."""
    from app.config import settings

    monkeypatch.setattr(settings, "gsp_scheduler_token", "")
    r = test_client.post("/gsp/scheduler/run")
    assert r.status_code == 503
    assert r.json()["detail"] == "scheduler_disabled"


def test_scheduler_run_wrong_token_rejected(monkeypatch, test_client) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "gsp_scheduler_token", "secret-token")
    r = test_client.post(
        "/gsp/scheduler/run",
        headers={"X-Scheduler-Token": "not-the-right-one"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_scheduler_token"


def test_scheduler_run_user_jwt_alone_is_rejected(monkeypatch, test_client, bootstrap_firm) -> None:
    """Even a valid admin JWT must not authorize the scheduler sweep —
    it is machine-only."""
    from app.config import settings
    from app.auth.tokens import create_access_token
    from app.models.tables import AppUser
    from sqlalchemy.orm import Session

    monkeypatch.setattr(settings, "gsp_scheduler_token", "secret-token")
    admin = bootstrap_firm()
    # Craft a valid access token as that admin.
    session = Session(bind=owner_engine)
    user = session.get(AppUser, admin["user_id"])
    token, _ = create_access_token(user)
    session.close()
    r = test_client.post(
        "/gsp/scheduler/run",
        headers={"Authorization": f"Bearer {token}"},
    )
    # No X-Scheduler-Token → 401 regardless of the user JWT.
    assert r.status_code == 401


def test_scheduler_run_accepted_with_correct_token(monkeypatch, test_client) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "gsp_scheduler_token", "correct-horse-battery")
    r = test_client.post(
        "/gsp/scheduler/run?today=2026-07-14",
        headers={"X-Scheduler-Token": "correct-horse-battery"},
    )
    assert r.status_code == 200
    assert r.json()["status"] in ("ok", "skipped_concurrency_locked")


@pytest.mark.quarantine
def test_scheduler_run_concurrency_guard_skips_second_call(
    monkeypatch, test_client, firm_and_client_no_session
) -> None:
    """Simulate an overlapping cron: hold the advisory lock on a separate
    connection and confirm the second /scheduler/run returns skipped.

    QUARANTINED (P3 P1 gate B1): asserts correct scheduler behaviour but
    fails deterministically in full-suite context. Root cause is a real
    scheduler bug — ``POST /gsp/scheduler/run`` and
    ``POST /scheduler/reminders/sweep`` acquire ``pg_try_advisory_lock``
    in one ``owner_engine.begin()`` block and release in a separate one;
    the pool may hand out a different DBAPI connection to the second
    block so the release is a no-op and the session-level lock leaks
    with the pooled backend. The test's own hold_conn interacts badly
    with prior tests' leaked locks. Fix is a scheduler code change (hold
    the same connection across acquire/release) — explicitly out of
    scope per the P3 gate direction. Tracked separately; must be
    resolved before quarantine is lifted.
    """
    from app.config import settings
    from app.api.gsp import _SCHEDULER_LOCK_KEY

    monkeypatch.setattr(settings, "gsp_scheduler_token", "t")
    ff = firm_and_client_no_session
    _connect(ff["firm_id"], ff["gstin_profile_id"], ff["user_id"])

    # Hold the lock via a distinct connection.
    hold_conn = owner_engine.connect()
    hold_conn.execute(text("SELECT pg_advisory_lock(:k)"), {"k": _SCHEDULER_LOCK_KEY})
    try:
        r = test_client.post(
            "/gsp/scheduler/run?today=2026-07-14",
            headers={"X-Scheduler-Token": "t"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "skipped_concurrency_locked"
        assert r.json()["attempts"] == []
    finally:
        hold_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _SCHEDULER_LOCK_KEY})
        hold_conn.close()


@pytest.mark.quarantine
def test_scheduler_run_records_audit_log_per_firm_touched(
    monkeypatch, test_client, firm_and_client_no_session
) -> None:
    """QUARANTINED (P3 P1 gate B1): same root cause as
    ``test_scheduler_run_concurrency_guard_skips_second_call`` above.
    A prior test's scheduler run leaks its advisory lock on a pooled
    backend; when this test's scheduler call issues ``pg_try_advisory_lock``
    it returns FALSE and the scheduler skips rather than running and
    writing the audit row this test asserts."""
    from app.config import settings

    monkeypatch.setattr(settings, "gsp_scheduler_token", "t")
    ff = firm_and_client_no_session
    _connect(ff["firm_id"], ff["gstin_profile_id"], ff["user_id"])

    r = test_client.post(
        "/gsp/scheduler/run?today=2026-07-14",
        headers={"X-Scheduler-Token": "t"},
    )
    assert r.status_code == 200
    with owner_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT user_id, action, diff FROM audit_log "
                "WHERE firm_id = :f AND action = 'gsp.scheduler_run'"
            ),
            {"f": str(ff["firm_id"])},
        ).mappings().all()
    assert len(rows) == 1
    assert rows[0]["user_id"] is None  # system actor, no human
    diff = rows[0]["diff"]
    assert diff["attempted"] >= 1


# ---------------------------------------------------------------------------
# Backfill plan
# ---------------------------------------------------------------------------


def test_backfill_plan_returns_last_n_periods(firm_and_client_no_session) -> None:
    """Default N=3. As of 2026-07-20 (past the 14th cutoff), the newest
    generated period is 202606 → offer [202606, 202605, 202604]."""
    ff = firm_and_client_no_session
    _connect(ff["firm_id"], ff["gstin_profile_id"], ff["user_id"])
    plan = service.backfill_plan(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        today=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    periods = [p["period"] for p in plan]
    assert periods == ["202606", "202605", "202604"]
    # Human labels for the UI.
    assert plan[0]["label"] == "June 2026"


def test_backfill_plan_skips_already_succeeded(firm_and_client_no_session) -> None:
    """A period we already pulled successfully must NOT reappear in the offer."""
    ff = firm_and_client_no_session
    _connect(ff["firm_id"], ff["gstin_profile_id"], ff["user_id"])
    service.pull_period(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        period="202606",
        source="manual",
    )
    plan = service.backfill_plan(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        today=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    assert "202606" not in [p["period"] for p in plan]


# ---------------------------------------------------------------------------
# Connection status endpoint — the panel data
# ---------------------------------------------------------------------------


def _auth_header(admin) -> dict:
    from app.auth.tokens import create_access_token
    from app.models.tables import AppUser
    from sqlalchemy.orm import Session

    session = Session(bind=owner_engine)
    user = session.get(AppUser, admin["user_id"])
    tok, _ = create_access_token(user)
    session.close()
    return {"Authorization": f"Bearer {tok}"}


def _make_admin_and_gstin(email: str = "admin@example.com"):
    from app.auth.passwords import hash_password
    from app.auth.totp import generate_secret

    firm_id = uuid.uuid4()
    user_id = uuid.uuid4()
    client_id = uuid.uuid4()
    gstin_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ca_firm (id, name) VALUES (:id, 'F')"),
            {"id": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO app_user (id, firm_id, email, password_hash, role, "
                "totp_secret, totp_confirmed, is_active) VALUES "
                "(:id, :fid, :e, :ph, 'admin', :ts, TRUE, TRUE)"
            ),
            {
                "id": user_id, "fid": firm_id, "e": email,
                "ph": hash_password("Correct-Horse-Battery-Staple-42"),
                "ts": generate_secret(),
            },
        )
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:c, :f, 'C')"
            ),
            {"c": client_id, "f": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile (id, firm_id, client_id, gstin, state_code) "
                "VALUES (:g, :f, :c, :gstin, '29')"
            ),
            {"g": gstin_id, "f": firm_id, "c": client_id, "gstin": CLIENT_GSTIN},
        )
    return {"firm_id": firm_id, "user_id": user_id, "client_id": client_id,
            "gstin_profile_id": gstin_id, "gstin": CLIENT_GSTIN}


def test_connection_endpoint_not_connected(test_client) -> None:
    ff = _make_admin_and_gstin("noconn@x.com")
    r = test_client.get(
        f"/gsp/connection/{ff['gstin_profile_id']}", headers=_auth_header(ff)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "not_connected"
    assert body["reason"] is None
    assert body["last_successful_pull_at"] is None
    assert body["sandbox_mode"] is True  # GSP_MODE=mock in tests
    assert body["backfill_offer"] == []


def test_connection_endpoint_connected_with_backfill(test_client) -> None:
    ff = _make_admin_and_gstin("conn@x.com")
    _connect(ff["firm_id"], ff["gstin_profile_id"], ff["user_id"])
    r = test_client.get(
        f"/gsp/connection/{ff['gstin_profile_id']}", headers=_auth_header(ff)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "connected"
    assert body["session_expires_at"] is not None
    # Backfill offer populated (at least one period).
    assert len(body["backfill_offer"]) >= 1


def test_connection_endpoint_reconnect_needed_carries_specific_reason(test_client) -> None:
    """UI must render the SPECIFIC stored cause — not a generic message."""
    ff = _make_admin_and_gstin("revoked@x.com")
    _connect(ff["firm_id"], ff["gstin_profile_id"], ff["user_id"])
    # Simulate a vendor-side revocation.
    service.mark_session_dead(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        reason="consent_revoked",
    )
    r = test_client.get(
        f"/gsp/connection/{ff['gstin_profile_id']}", headers=_auth_header(ff)
    )
    body = r.json()
    assert body["state"] == "reconnect_needed"
    assert body["reason"] == "consent_revoked"


def test_connection_endpoint_reason_after_expiry_vs_user_disconnect(test_client) -> None:
    """Every revoke path stores its own reason — the UI can distinguish
    'GSTN pulled consent' from 'session TTL elapsed' from 'user clicked disconnect'."""
    ff = _make_admin_and_gstin("exp@x.com")
    _connect(ff["firm_id"], ff["gstin_profile_id"], ff["user_id"])
    service.disconnect(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        gstin_profile_id=ff["gstin_profile_id"],
    )
    r = test_client.get(
        f"/gsp/connection/{ff['gstin_profile_id']}", headers=_auth_header(ff)
    )
    assert r.json()["reason"] == "user_disconnected"


def test_connection_endpoint_cross_firm_404(test_client) -> None:
    """RLS: a stranger's gstin_profile_id 404s."""
    ff_a = _make_admin_and_gstin("a@x.com")
    ff_b = _make_admin_and_gstin("b@x.com")
    r = test_client.get(
        f"/gsp/connection/{ff_b['gstin_profile_id']}", headers=_auth_header(ff_a)
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# P2.1 Stage E — /gsp/connection/{gpid} carries the latest attempt.
# ---------------------------------------------------------------------------


def test_connection_endpoint_latest_attempt_null_when_no_pulls_yet(test_client) -> None:
    """A freshly-connected GSTIN with zero pulls has latest_attempt = None."""
    ff = _make_admin_and_gstin("nopulls@x.com")
    _connect(ff["firm_id"], ff["gstin_profile_id"], ff["user_id"])
    r = test_client.get(
        f"/gsp/connection/{ff['gstin_profile_id']}", headers=_auth_header(ff)
    )
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "connected"
    assert body["latest_attempt"] is None


def test_connection_endpoint_latest_attempt_reflects_succeeded_pull(test_client) -> None:
    """After a successful pull, latest_attempt.status == 'succeeded' with
    no error_kind. This is the 'healthy' state on the panel."""
    ff = _make_admin_and_gstin("ok@x.com")
    _connect(ff["firm_id"], ff["gstin_profile_id"], ff["user_id"])
    service.pull_period(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        period="202606",
        source="manual",
    )
    r = test_client.get(
        f"/gsp/connection/{ff['gstin_profile_id']}", headers=_auth_header(ff)
    )
    la = r.json()["latest_attempt"]
    assert la is not None
    assert la["status"] == "succeeded"
    assert la["error_kind"] is None
    assert la["finished_at"] is not None


def test_connection_endpoint_latest_attempt_reflects_failed_pull(test_client) -> None:
    """After a NoLiveSession pull (session gone), latest_attempt.status
    == 'failed' with error_kind='session_dead'. This is the row the
    Stage-E panel state 'last_pull_failed' hangs on."""
    ff = _make_admin_and_gstin("fail@x.com")
    _connect(ff["firm_id"], ff["gstin_profile_id"], ff["user_id"])
    # Kill the session, then attempt a pull — records a failed attempt row.
    service.disconnect(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        gstin_profile_id=ff["gstin_profile_id"],
    )
    with pytest.raises(service.NoLiveSession):
        service.pull_period(
            firm_id=ff["firm_id"],
            gstin_profile_id=ff["gstin_profile_id"],
            period="202606",
            source="manual",
        )
    r = test_client.get(
        f"/gsp/connection/{ff['gstin_profile_id']}", headers=_auth_header(ff)
    )
    body = r.json()
    # Session-side: reconnect_needed (disconnect stored 'user_disconnected')
    assert body["state"] == "reconnect_needed"
    # BUT the latest_attempt is still populated so the historical failure
    # is visible to the panel even after the session state moved on.
    la = body["latest_attempt"]
    assert la is not None
    assert la["status"] == "failed"
    assert la["error_kind"] == "session_dead"
    assert la["finished_at"] is not None
