"""E2 blast-radius diagnostic — NOT a permanent test; do not merge without review.

If the /gsp/scheduler/run advisory-lock guard ever fails to guard (e.g. the
release-on-different-connection defect documented on the two quarantined
tests in test_gsp_stage4_surface.py), what does the schema let through?

This file exercises the *schema*, bypassing the guard, so the answer is
independent of whether the guard is currently working.

Reports (via assertion messages):
  * gstn_pull duplicates for (gstin_profile_id, period)
  * b2b_entry double-count → ITC double-count
  * audit_log duplicates for a single scheduler run
  * delivery_request duplicates (reminders sweep — protected by unique idx)

Run with:
    pytest tests/integration/test_scheduler_blast_radius.py -q --no-cov -s
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
from sqlalchemy import text

from app.auth import audit
from app.db import firm_scoped_session, owner_engine
from app.gsp import service
from app.gsp.mock_server import FIXED_OTP, app as mock_app


CLIENT_GSTIN = "29ZZZZZ9999Z9Z9"


def _free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def mock_gsp():
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
    yield base
    server.should_exit = True
    t.join(timeout=5)


@pytest.fixture(autouse=True)
def _point_service_at_mock(mock_gsp, monkeypatch):
    from app.gsp import adapter_mock, service as svc
    monkeypatch.setattr(
        svc, "get_adapter", lambda: adapter_mock.MockGSPAdapter(base_url=mock_gsp)
    )
    svc._inflight.clear()
    from app.gsp import mock_server as m
    m._sessions.clear()
    m._consent_requests.clear()


def _seeded():
    firm_id = uuid.uuid4()
    user_id = uuid.uuid4()
    client_id = uuid.uuid4()
    gstin_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(text("INSERT INTO ca_firm (id, name) VALUES (:id, 'BLAST')"), {"id": firm_id})
        conn.execute(
            text(
                "INSERT INTO app_user (id, firm_id, email, password_hash, role, "
                "totp_confirmed, is_active) VALUES "
                "(:id, :fid, 'b@x.com', 'x', 'admin', TRUE, TRUE)"
            ),
            {"id": user_id, "fid": firm_id},
        )
        conn.execute(
            text("INSERT INTO client (id, firm_id, trade_name) VALUES (:c, :f, 'C')"),
            {"c": client_id, "f": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile (id, firm_id, client_id, gstin, state_code) "
                "VALUES (:g, :f, :c, :gstin, '29')"
            ),
            {"g": gstin_id, "f": firm_id, "c": client_id, "gstin": CLIENT_GSTIN},
        )
    r = service.initiate_consent(firm_id=firm_id, gstin_profile_id=gstin_id, user_id=user_id)
    service.confirm_consent(firm_id=firm_id, user_id=user_id, inflight_id=r.inflight_id, otp=FIXED_OTP)
    return firm_id, gstin_id


def test_blast_two_concurrent_pulls_same_period_duplicate_gstn_pull_rows():
    """WHAT HAPPENS if the guard fails and two overlapping runs both call
    pull_period(firm, gstin, period='202606')?

    Expected schema-level behaviour: gstn_pull has no UNIQUE on
    (gstin_profile_id, period) → both INSERTs succeed → two rows → two
    b2b_entry sets → ITC totals from b2b_entry double.
    """
    firm_id, gstin_id = _seeded()
    period = "202606"

    barrier = threading.Barrier(2)
    errors: list[Exception] = []
    def _fire():
        try:
            barrier.wait(timeout=5)
            service.pull_period(
                firm_id=firm_id, gstin_profile_id=gstin_id,
                period=period, source="scheduled",
            )
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=_fire)
    t2 = threading.Thread(target=_fire)
    t1.start(); t2.start()
    t1.join(timeout=15); t2.join(timeout=15)

    with owner_engine.begin() as conn:
        pull_rows = conn.execute(
            text(
                "SELECT COUNT(*) FROM gstn_pull "
                "WHERE gstin_profile_id=:g AND period=:p"
            ),
            {"g": str(gstin_id), "p": period},
        ).scalar_one()
        entry_rows = conn.execute(
            text(
                "SELECT COUNT(*) FROM b2b_entry b "
                "JOIN gstn_pull p ON p.id=b.gstn_pull_id "
                "WHERE p.gstin_profile_id=:g AND p.period=:p"
            ),
            {"g": str(gstin_id), "p": period},
        ).scalar_one()

    print(f"\n[BLAST] errors={len(errors)} gstn_pull_rows={pull_rows} b2b_entry_rows={entry_rows}")
    for e in errors:
        print(f"[BLAST] error={type(e).__name__}: {e}")

    # This assert intentionally documents current (unsafe) behaviour rather
    # than what we want it to be — the point of this file is to REVEAL, not
    # prevent. If schema-level dedup is later added and this test starts
    # returning 1, delete it — the blast is fixed.
    assert pull_rows in (1, 2), f"unexpected pull count {pull_rows}"
    if pull_rows == 2:
        print("[BLAST] CONFIRMED: gstn_pull duplication is possible when the guard fails.")


def test_blast_two_audit_log_rows_from_two_scheduler_runs():
    """audit_log has no uniqueness on (firm_id, action, at). Two overlapping
    scheduler runs would each record their own gsp.scheduler_run row.
    """
    firm_id, gstin_id = _seeded()
    for _ in range(2):
        with firm_scoped_session(firm_id) as db:
            audit.record(
                db,
                firm_id=firm_id,
                actor_user_id=None,
                action="gsp.scheduler_run",
                entity_type="ca_firm",
                entity_id=firm_id,
                metadata={"today": "2026-07-14", "attempted": 1},
            )
    with owner_engine.begin() as conn:
        n = conn.execute(
            text(
                "SELECT COUNT(*) FROM audit_log "
                "WHERE firm_id=:f AND action='gsp.scheduler_run'"
            ),
            {"f": str(firm_id)},
        ).scalar_one()
    print(f"\n[BLAST] audit_log rows for one firm's scheduler_run={n}")
    assert n == 2, "audit_log accepts duplicate scheduler_run rows — no dedup"
