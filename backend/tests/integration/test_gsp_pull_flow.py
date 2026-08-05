"""Stage 3 integration tests — pull path, retry, scheduler, ITC split,
ingestion-parity, monthly usage, failure surface.

Entry-criteria coverage:

    (1) matched-bucket ITC split (fixture-driven)   → test_itc_split_*
    (2) scheduled pull uses rule-pack knob + Pull-now → test_scheduler_*, test_pull_now_*
    (3) GSP pull and JSON upload produce identical recon summaries
                                                     → test_gsp_pull_recon_identical_to_json_upload
    (4) retry policy per taxonomy (mid-integration)  → test_pull_retries_gstn_down_and_succeeds,
                                                     test_pull_does_not_retry_session_expired
    (5) call metering (period + error_kind) + monthly count
                                                     → test_call_log_populates_*, test_monthly_call_count
    (6) failed scheduled pull leaves a loud, queryable state
                                                     → test_failed_scheduled_pull_visible_in_attempts
"""
from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

import pytest
import uvicorn
from sqlalchemy import text

from app.db import app_engine, owner_engine
from app.gsp import service
from app.gsp.mock_server import FIXED_OTP, app as mock_app


FIXTURE_DIR = Path(__file__).parent.parent.parent / "app" / "gsp" / "fixtures"
CLIENT_GSTIN = "29ZZZZZ9999Z9Z9"


# ---------------------------------------------------------------------------
# In-process mock server fixture (shared with consent flow tests style)
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
# Firm + GSTIN + register seed
# ---------------------------------------------------------------------------


@pytest.fixture
def firm_with_connected_gstin():
    """Firm + user + client + gstin_profile + LIVE gsp_session via the
    real consent flow (encrypted, audited, everything)."""
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
    r = service.initiate_consent(
        firm_id=firm_id, gstin_profile_id=gstin_id, user_id=user_id
    )
    service.confirm_consent(
        firm_id=firm_id, user_id=user_id, inflight_id=r.inflight_id, otp=FIXED_OTP
    )
    return {
        "firm_id": firm_id,
        "user_id": user_id,
        "client_id": client_id,
        "gstin_profile_id": gstin_id,
        "gstin": CLIENT_GSTIN,
    }


# ---------------------------------------------------------------------------
# (2) Pull-now — reuses the JSON ingestion path
# ---------------------------------------------------------------------------


def test_pull_now_creates_gstn_pull_with_source_gsp_api(firm_with_connected_gstin) -> None:
    ff = firm_with_connected_gstin
    result = service.pull_period(
        firm_id=ff["firm_id"],
        gstin_profile_id=ff["gstin_profile_id"],
        period="202606",
        source="manual",
    )
    with owner_engine.begin() as conn:
        row = conn.execute(
            text("SELECT source, period FROM gstn_pull WHERE id = :id"),
            {"id": str(result.gstn_pull_id)},
        ).one()
    assert row[0] == "gsp_api"
    assert row[1] == "202606"
    # Every b2b_entry from the fixture landed via the shared writer.
    with owner_engine.begin() as conn:
        (n,) = conn.execute(
            text(
                "SELECT COUNT(*) FROM b2b_entry WHERE gstn_pull_id = :id"
            ),
            {"id": str(result.gstn_pull_id)},
        ).one()
    assert n == 3  # matches the June 2026 fixture


def test_no_live_session_raises_and_is_queryable(firm_with_connected_gstin) -> None:
    ff = firm_with_connected_gstin
    # Kill the session.
    service.disconnect(
        firm_id=ff["firm_id"],
        user_id=ff["user_id"],
        gstin_profile_id=ff["gstin_profile_id"],
    )
    with pytest.raises(service.NoLiveSession):
        service.pull_period(
            firm_id=ff["firm_id"],
            gstin_profile_id=ff["gstin_profile_id"],
            period="202606",
            source="manual",
        )
    # Attempt row exists, status=failed, error_kind=session_dead.
    with owner_engine.begin() as conn:
        r = conn.execute(
            text(
                "SELECT status, error_kind FROM gsp_pull_attempt "
                "WHERE gstin_profile_id = :g"
            ),
            {"g": str(ff["gstin_profile_id"])},
        ).one()
    assert r == ("failed", "session_dead")


# ---------------------------------------------------------------------------
# (3) Ingestion parity: GSP pull vs JSON upload produce identical recon
# ---------------------------------------------------------------------------


def _seed_matching_register(firm_id, gstin_profile_id, ctin: str) -> None:
    """Register invoices that will match the June 2026 fixture exactly."""
    with owner_engine.begin() as conn:
        # INV-2026-100 total ₹1180  (100_000 taxable + 9k+9k CGST/SGST)
        # INV-2026-101 total ₹2360  (200_000 taxable + 36k IGST)
        # INV-2026-102 total ₹1770  (150_000 taxable + 13.5k+13.5k) — itc_not_available
        for inum, idt, total, taxable, cgst, sgst, igst in [
            ("INV-2026-100", "2026-06-05", 118000, 100000, 9000, 9000, 0),
            ("INV-2026-101", "2026-06-12", 236000, 200000, 0, 0, 36000),
            ("INV-2026-102", "2026-06-22", 177000, 150000, 13500, 13500, 0),
        ]:
            conn.execute(
                text(
                    """
                    INSERT INTO invoice (
                        firm_id, gstin_profile_id, source, direction,
                        invoice_number, invoice_date, counterparty_gstin,
                        taxable_value_paise, cgst_paise, sgst_paise, igst_paise,
                        total_paise, content_hash
                    ) VALUES (
                        :fid, :gid, 'csv_import', 'purchase',
                        :inum, CAST(:idt AS DATE), :ctin,
                        :tx, :c, :s, :i,
                        :tot, :h
                    )
                    """
                ),
                {
                    "fid": str(firm_id),
                    "gid": str(gstin_profile_id),
                    "inum": inum,
                    "idt": idt,
                    "ctin": ctin,
                    "tx": taxable,
                    "c": cgst,
                    "s": sgst,
                    "i": igst,
                    "tot": total,
                    "h": f"seed-{inum}",
                },
            )


def _run_recon(firm_id, gstin_profile_id, period: str):
    from app.engines.reconciliation.service import reconcile_period

    r = reconcile_period(firm_id, gstin_profile_id, period)
    return r.summary


def _pull_via_json_upload(firm_id, gstin_profile_id) -> None:
    """Simulate the JSON-upload path by calling the shared writer with
    the fixture — exact same code the RQ worker runs."""
    from app.ingestion.gstr2b_parser import parse_gstr2b_json
    from app.ingestion.writer import bulk_insert_b2b_entries, insert_gstn_pull

    with open(FIXTURE_DIR / f"gstr2b_{CLIENT_GSTIN}_202606.json") as f:
        payload = json.load(f)
    pull_id = insert_gstn_pull(
        firm_id=firm_id, gstin_profile_id=gstin_profile_id,
        period="202606", raw_payload=payload, source="json_import",
    )
    parse = parse_gstr2b_json(payload, gstn_pull_id=str(pull_id))
    bulk_insert_b2b_entries(
        firm_id=firm_id, gstn_pull_id=pull_id, entries=parse.entries
    )


def test_gsp_pull_recon_identical_to_json_upload(firm_with_connected_gstin) -> None:
    """This is the load-bearing "no fork" proof.

    Set up two identical firms; one ingests via GSP pull, the other via
    JSON upload of the same fixture. Reconciliation summaries must be
    byte-identical modulo the source field on gstn_pull (which is the
    ONE thing that legitimately differs).
    """
    ff = firm_with_connected_gstin
    # A second firm, second gstin, second connected session — for the JSON path.
    firm2 = uuid.uuid4()
    user2 = uuid.uuid4()
    client2 = uuid.uuid4()
    gstin2 = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ca_firm (id, name) VALUES (:id, 'Second Firm')"),
            {"id": firm2},
        )
        conn.execute(
            text(
                "INSERT INTO app_user (id, firm_id, email, password_hash, role, "
                "totp_confirmed, is_active) VALUES (:id, :fid, 'b@x.com', 'x', 'admin', TRUE, TRUE)"
            ),
            {"id": user2, "fid": firm2},
        )
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) VALUES (:cid, :fid, 'Acme2')"
            ),
            {"cid": client2, "fid": firm2},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile (id, firm_id, client_id, gstin, state_code) "
                "VALUES (:gid, :fid, :cid, :g, '29')"
            ),
            {"gid": gstin2, "fid": firm2, "cid": client2, "g": CLIENT_GSTIN},
        )

    # Same register on both.
    _seed_matching_register(
        ff["firm_id"], ff["gstin_profile_id"], "29AAAAA0000A1Z5"
    )
    _seed_matching_register(firm2, gstin2, "29AAAAA0000A1Z5")

    # GSP pull on firm 1.
    service.pull_period(
        firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
        period="202606", source="manual",
    )
    # JSON upload on firm 2.
    _pull_via_json_upload(firm2, gstin2)

    a = _run_recon(ff["firm_id"], ff["gstin_profile_id"], "202606")
    b = _run_recon(firm2, gstin2, "202606")
    # Same summary — every count, every paise total, every top_supplier row.
    assert a == b, f"recon summaries diverged:\nGSP: {a}\nJSON:{b}"


# ---------------------------------------------------------------------------
# (1) ITC split — fixture-driven
# ---------------------------------------------------------------------------


def test_itc_split_respects_itc_available_on_matched(firm_with_connected_gstin) -> None:
    """Two ITC-available (₹1180 + ₹2360) + one not-available (₹1770).
    matched.paise = 5310 rupees; paise_claimable = 3540; paise_not_available = 1770."""
    ff = firm_with_connected_gstin
    _seed_matching_register(
        ff["firm_id"], ff["gstin_profile_id"], "29AAAAA0000A1Z5"
    )
    service.pull_period(
        firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
        period="202606", source="manual",
    )
    summary = _run_recon(ff["firm_id"], ff["gstin_profile_id"], "202606")
    m = summary["matched"]
    # (118000 + 236000 + 177000) paise = 531000
    assert m["count"] == 3
    assert m["paise"] == 531_000
    assert m["paise_claimable"] == 118_000 + 236_000  # 354000
    assert m["paise_not_available"] == 177_000
    # Sanity: split adds up.
    assert m["paise_claimable"] + m["paise_not_available"] == m["paise"]


# ---------------------------------------------------------------------------
# (4) Retry policy — end-to-end via mock's failure-injection primitive
# ---------------------------------------------------------------------------


def _install_failing_adapter(monkeypatch, mock_url: str, fail: str, then_ok_after: int):
    """Wrap MockGSPAdapter so its fetch_gstr2b returns failure ``fail``
    ``then_ok_after`` times, then succeeds."""
    from app.gsp import adapter_mock, service as svc

    counter = {"n": 0}

    class FlakyAdapter(adapter_mock.MockGSPAdapter):
        def fetch_gstr2b(self, session, gstin, period):
            counter["n"] += 1
            if counter["n"] <= then_ok_after:
                # Hit the mock with the fail query — its taxonomy translation
                # returns the correct exception.
                import httpx
                resp = httpx.post(
                    f"{mock_url}/gsp/v1/gstr2b?fail={fail}",
                    json={"token": session.token, "gstin": gstin, "period": period},
                    timeout=5,
                )
                from app.gsp.adapter_mock import _translate

                _translate(resp)  # raises
            return super().fetch_gstr2b(session, gstin, period)

    monkeypatch.setattr(svc, "get_adapter", lambda: FlakyAdapter(base_url=mock_url))


def test_pull_retries_gstn_down_and_succeeds(
    firm_with_connected_gstin, mock_gsp_server, monkeypatch
) -> None:
    ff = firm_with_connected_gstin
    _install_failing_adapter(
        monkeypatch, mock_gsp_server, fail="gstn_down", then_ok_after=2
    )
    # Inject a zero-wait policy so the test doesn't sleep for real.
    from app.gsp import retry

    monkeypatch.setattr(
        retry,
        "load_policy",
        lambda: retry.RetryPolicy(
            max_attempts=3,
            gstn_unavailable_backoff=[0, 0, 0],
            rate_limited_default=0,
        ),
    )
    r = service.pull_period(
        firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
        period="202606", source="manual",
    )
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT status, attempt_count, error_kind FROM gsp_pull_attempt "
                "WHERE id = :id"
            ),
            {"id": str(r.attempt_id)},
        ).one()
    assert row[0] == "succeeded"
    assert row[1] == 3  # counted every attempt


def test_pull_does_not_retry_session_expired(
    firm_with_connected_gstin, mock_gsp_server, monkeypatch
) -> None:
    """SESSION_EXPIRED never retries and marks the session dead."""
    ff = firm_with_connected_gstin
    _install_failing_adapter(
        monkeypatch, mock_gsp_server, fail="session_expired", then_ok_after=999
    )
    from app.gsp import retry
    from app.gsp.client import SessionExpired

    monkeypatch.setattr(
        retry,
        "load_policy",
        lambda: retry.RetryPolicy(
            max_attempts=3,
            gstn_unavailable_backoff=[0, 0, 0],
            rate_limited_default=0,
        ),
    )
    with pytest.raises(SessionExpired):
        service.pull_period(
            firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
            period="202606", source="manual",
        )
    # gsp_session row is marked dead — reconnect required.
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT revoked_at, revoked_reason FROM gsp_session "
                "WHERE gstin_profile_id = :g"
            ),
            {"g": str(ff["gstin_profile_id"])},
        ).one()
    assert row[0] is not None
    assert row[1] == "session_expired"


def test_pull_rate_limited_honors_retry_after_from_header(
    firm_with_connected_gstin, mock_gsp_server, monkeypatch
) -> None:
    ff = firm_with_connected_gstin
    _install_failing_adapter(
        monkeypatch, mock_gsp_server, fail="rate_limited", then_ok_after=1
    )
    waits: list[float] = []
    from app.gsp import retry

    monkeypatch.setattr(
        retry,
        "load_policy",
        lambda: retry.RetryPolicy(
            max_attempts=3, gstn_unavailable_backoff=[0], rate_limited_default=99,
        ),
    )
    # Replace time.sleep in retry
    monkeypatch.setattr(
        retry.time, "sleep", lambda s: waits.append(s), raising=True
    )
    r = service.pull_period(
        firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
        period="202606", source="manual",
    )
    del r
    # Mock sends Retry-After: 30 → policy uses 30, not the 99 default.
    assert waits == [30]


# ---------------------------------------------------------------------------
# (5) Call metering: period + error_kind + monthly rollup
# ---------------------------------------------------------------------------


def test_call_log_populates_period_and_error_kind_on_pull(firm_with_connected_gstin) -> None:
    ff = firm_with_connected_gstin
    service.pull_period(
        firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
        period="202606", source="manual",
    )
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT endpoint, period, succeeded, error_kind, latency_ms "
                "FROM gsp_call_log WHERE endpoint = 'gstr2b' "
                "ORDER BY at DESC LIMIT 1"
            )
        ).one()
    assert row[0] == "gstr2b"
    assert row[1] == "202606"
    assert row[2] is True
    assert row[3] is None
    assert row[4] >= 0


def test_monthly_call_count_rolls_up_by_endpoint(firm_with_connected_gstin) -> None:
    ff = firm_with_connected_gstin
    service.pull_period(
        firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
        period="202606", source="manual",
    )
    # Do a second pull to make sure the count increases.
    service.pull_period(
        firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
        period="202605", source="manual",
    )
    now = datetime.now(tz=timezone.utc)
    month = f"{now.year:04d}{now.month:02d}"
    data = service.monthly_call_count(firm_id=ff["firm_id"], month=month)
    by_ep = {r["endpoint"]: r for r in data["per_endpoint"]}
    # consent (1) + confirm (1) + gstr2b (2) at minimum, all under this firm.
    assert by_ep["gstr2b"]["total"] >= 2
    assert by_ep["gstr2b"]["successes"] >= 2
    assert data["total_calls"] >= 4


def test_initiate_cooldown_records_call_log_row(firm_with_connected_gstin) -> None:
    """SMS-flood block populates a gsp_call_log row with error_kind=initiate_cooldown."""
    ff = firm_with_connected_gstin
    # Reset in case previous tests bumped the counter for this GSTIN.
    # The cooldown-clear helper lives in tests/support/ (out of the app
    # package) — see P2.1 Stage C containment.
    from app.gsp import lockout
    from tests.support.lockout_admin import clear_gsp_initiate_cooldown_for_gstin

    clear_gsp_initiate_cooldown_for_gstin(ff["gstin"])
    # Exhaust the per-hour cap, then the next attempt must block.
    for _ in range(lockout.INITIATE_MAX_PER_HOUR):
        service.initiate_consent(
            firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
            user_id=ff["user_id"],
        )
    with pytest.raises(service.InitiateCooldown):
        service.initiate_consent(
            firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
            user_id=ff["user_id"],
        )
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT COUNT(*) FROM gsp_call_log "
                "WHERE endpoint = 'consent' AND error_kind = 'initiate_cooldown' "
                "AND firm_id = :f"
            ),
            {"f": str(ff["firm_id"])},
        ).scalar_one()
    assert row >= 1


# ---------------------------------------------------------------------------
# (6) Loud, queryable failure state
# ---------------------------------------------------------------------------


def test_failed_scheduled_pull_visible_in_attempts(firm_with_connected_gstin) -> None:
    ff = firm_with_connected_gstin
    service.disconnect(
        firm_id=ff["firm_id"], user_id=ff["user_id"],
        gstin_profile_id=ff["gstin_profile_id"],
    )
    # A scheduled pull with no live session must record a failed attempt row
    # so the UI can surface it — silent failure is the forbidden outcome.
    with pytest.raises(service.NoLiveSession):
        service.pull_period(
            firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
            period="202606", source="scheduled",
        )
    with owner_engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT status, source, error_kind, error_message, finished_at "
                "FROM gsp_pull_attempt WHERE firm_id = :f"
            ),
            {"f": str(ff["firm_id"])},
        ).all()
    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "failed"
    assert row[1] == "scheduled"
    assert row[2] == "session_dead"
    assert row[3]  # non-empty message
    assert row[4] is not None  # finished_at populated so it's not "running"


# ---------------------------------------------------------------------------
# (2) Scheduler: due_periods respects the rule-pack knob
# ---------------------------------------------------------------------------


def test_due_periods_before_knob_returns_empty() -> None:
    # Rule pack knob = 14. On the 13th, nothing is due.
    day = datetime(2026, 8, 13, tzinfo=timezone.utc)
    assert service.due_periods_for_today(day) == []


def test_due_periods_after_knob_returns_previous_month() -> None:
    # On the 14th of August 2026, July 2026's 2B is due.
    day = datetime(2026, 8, 14, tzinfo=timezone.utc)
    assert service.due_periods_for_today(day) == ["202607"]


def test_scheduler_skips_gstins_already_succeeded(firm_with_connected_gstin) -> None:
    """A GSTIN with a succeeded attempt for the due period is not
    re-attempted — idempotent."""
    ff = firm_with_connected_gstin
    # Do a manual pull for period 202606 first.
    service.pull_period(
        firm_id=ff["firm_id"], gstin_profile_id=ff["gstin_profile_id"],
        period="202606", source="manual",
    )
    # Ask the scheduler what's due on 2026-07-14 — July 14 → June is the
    # previous period. Our GSTIN already succeeded for 202606 → skip.
    due = service.find_gstins_due(datetime(2026, 7, 14, tzinfo=timezone.utc))
    assert all(
        gpid != ff["gstin_profile_id"] or period != "202606"
        for _, gpid, period in due
    )


def test_scheduler_returns_reports_and_records_pull_attempts(firm_with_connected_gstin) -> None:
    ff = firm_with_connected_gstin
    reports = service.run_scheduled_pulls(
        datetime(2026, 7, 14, tzinfo=timezone.utc)
    )
    # One (firm, gstin) × period 202606 due; report present.
    my = [r for r in reports if r["gstin_profile_id"] == str(ff["gstin_profile_id"])]
    assert len(my) == 1
    assert my[0]["status"] == "succeeded"
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT status, source FROM gsp_pull_attempt "
                "WHERE gstin_profile_id = :g AND period = :p"
            ),
            {"g": str(ff["gstin_profile_id"]), "p": "202606"},
        ).one()
    assert row == ("succeeded", "scheduled")
