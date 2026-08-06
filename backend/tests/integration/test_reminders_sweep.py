"""Due-date reminder sweep — dispatch, idempotency, filed-skip, auth."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.config import settings
from app.db import owner_engine
from app.email import MemoryTransport, reset_transport_for_tests


@pytest.fixture
def firm_with_gid():
    """Seed a firm + admin + client + gstin_profile via owner engine.

    Returns dict(firm_id, admin_user_id, admin_email, client_id, gid_id,
    gstin, trade_name). The admin_user_id is the sole recipient the
    sweep should nudge (staff-assignment is unused here).
    """
    firm_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    client_id = uuid.uuid4()
    gid_id = uuid.uuid4()
    gstin = "29ABCDE1234F1Z5"
    admin_email = f"rem-admin-{firm_id.hex[:6]}@example.com"

    from app.auth.passwords import hash_password

    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ca_firm (id, name) VALUES (:id, 'Firm R')"),
            {"id": firm_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO app_user (id, firm_id, email, password_hash, role,
                                       totp_confirmed, is_active)
                VALUES (:id, :fid, :email, :ph, 'admin', TRUE, TRUE)
                """
            ),
            {
                "id": admin_id, "fid": firm_id, "email": admin_email,
                "ph": hash_password("Correct-Horse-Battery-Staple-42"),
            },
        )
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:cid, :fid, 'Ramesh Textiles')"
            ),
            {"cid": client_id, "fid": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code) "
                "VALUES (:gid, :fid, :cid, :gstin, :state)"
            ),
            {
                "gid": gid_id, "fid": firm_id, "cid": client_id,
                "gstin": gstin, "state": gstin[:2],
            },
        )

    return {
        "firm_id": firm_id, "admin_user_id": admin_id, "admin_email": admin_email,
        "client_id": client_id, "gid_id": gid_id, "gstin": gstin,
        "trade_name": "Ramesh Textiles",
    }


@pytest.fixture
def memory_email(monkeypatch):
    monkeypatch.setattr(settings, "email_enabled", True)
    monkeypatch.setattr(settings, "email_app_base_url", "https://app.example.test")
    monkeypatch.setattr(settings, "reminders_enabled", True)
    mem = MemoryTransport()
    reset_transport_for_tests(mem)
    yield mem
    reset_transport_for_tests(None)


def _due_date_for_period(period: str, day: int) -> date:
    """Mirror of _compute_due_date — GSTR-3B day 20, GSTR-1 day 11 in
    the FOLLOWING month. Kept here so tests don't reach into internals."""
    from calendar import monthrange
    y, m = int(period[:4]), int(period[4:])
    if m == 12:
        y2, m2 = y + 1, 1
    else:
        y2, m2 = y, m + 1
    d = min(day, monthrange(y2, m2)[1])
    return date(y2, m2, d)


def test_sweep_dispatches_gstr3b_at_seven_days(firm_with_gid, memory_email) -> None:
    from app.reminders import sweep_reminders

    # GSTR-3B for period 202607 is due 2026-08-20 (day 20 of following month).
    # We simulate "today" = 2026-08-13 so days_out = 7 → matches threshold.
    # GSTR-1 for the same period was due 2026-08-11 (already past) — the
    # only in-window candidate on this day is the single GSTR-3B send to
    # the sole admin recipient.
    today = date(2026, 8, 13)
    report = sweep_reminders(today)

    assert report.dispatched == 1, f"report={report}"
    assert len(memory_email.sent) == 1
    msg = memory_email.sent[0]
    assert msg.to == firm_with_gid["admin_email"]
    assert "GSTR3B" in msg.subject
    assert firm_with_gid["gstin"] in msg.subject
    assert "2026-08-20" in msg.subject or "2026-08-20" in msg.body_text


def test_sweep_is_idempotent_on_rerun(firm_with_gid, memory_email) -> None:
    from app.reminders import sweep_reminders

    today = date(2026, 8, 13)
    r1 = sweep_reminders(today)
    first_count = r1.dispatched
    assert first_count > 0

    # Second run same day: every candidate row is already in reminder_log,
    # so every attempted insert conflicts and no email fires.
    memory_email.clear()
    r2 = sweep_reminders(today)
    assert r2.dispatched == 0
    assert r2.skipped_duplicate >= first_count
    assert memory_email.sent == []


def test_sweep_skips_filed_period(firm_with_gid, memory_email) -> None:
    """A period whose filing_run.status == 'filed' must not be nudged."""
    from app.reminders import sweep_reminders

    today = date(2026, 8, 13)
    # Insert a filed filing_run for GSTR-3B 202607 via owner engine.
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO filing_run (
                    firm_id, gstin_profile_id, return_type, period,
                    status, payload, rule_pack_version
                ) VALUES (
                    :fid, :gid, 'GSTR3B', '202607',
                    'filed', '{}'::jsonb, 'v-test'
                )
                """
            ),
            {"fid": firm_with_gid["firm_id"], "gid": firm_with_gid["gid_id"]},
        )

    report = sweep_reminders(today)
    # Should have skipped the GSTR-3B send for the filed period.
    assert report.skipped_filed >= 1
    subjects = " | ".join(m.subject for m in memory_email.sent)
    # No GSTR-3B email for the filed period.
    assert "GSTR3B" not in subjects or "202607" not in subjects


def test_sweep_disabled_is_noop(firm_with_gid, memory_email, monkeypatch) -> None:
    from app.reminders import sweep_reminders

    monkeypatch.setattr(settings, "reminders_enabled", False)
    report = sweep_reminders(date(2026, 8, 13))
    assert report.dispatched == 0
    assert report.firms_visited == 0  # early return, doesn't walk firms
    assert memory_email.sent == []


def test_sweep_not_at_threshold_skips(firm_with_gid, memory_email) -> None:
    """A day that lands outside every threshold should dispatch nothing."""
    from app.reminders import sweep_reminders

    # 2026-08-05 → GSTR-3B 202607 due 2026-08-20 = 15 days out (not in {7,3,1,0})
    #             GSTR-1 202607 due 2026-08-11 = 6 days out (not in {7,3,1,0})
    report = sweep_reminders(date(2026, 8, 5))
    assert report.dispatched == 0


def test_scheduler_endpoint_requires_token(test_client) -> None:
    r = test_client.post("/scheduler/reminders/sweep")
    # Empty gsp_scheduler_token in test config → 503 (endpoint disabled).
    assert r.status_code in (401, 503), r.text


def test_scheduler_endpoint_runs_sweep(
    test_client, firm_with_gid, memory_email, monkeypatch
) -> None:
    monkeypatch.setattr(settings, "gsp_scheduler_token", "sekret")
    r = test_client.post(
        "/scheduler/reminders/sweep",
        params={"today": "2026-08-13"},
        headers={"X-Scheduler-Token": "sekret"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["today"] == "2026-08-13"
    assert body["status"] == "ok"
    assert body["dispatched"] >= 1


def test_recipient_resolution_prefers_admin_over_assignment(
    firm_with_gid, memory_email
) -> None:
    """The firm admin is always a recipient. Add a staff user WITHOUT
    an assignment — they should NOT get the email. Add a staff WITH
    an assignment — they SHOULD."""
    from app.auth.passwords import hash_password
    from app.reminders import sweep_reminders

    staff_assigned = uuid.uuid4()
    staff_unassigned = uuid.uuid4()

    with owner_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO app_user (id, firm_id, email, password_hash, role,
                                       totp_confirmed, is_active)
                VALUES
                (:a, :fid, :ae, :ph, 'staff', TRUE, TRUE),
                (:u, :fid, :ue, :ph, 'staff', TRUE, TRUE)
                """
            ),
            {
                "a": staff_assigned, "u": staff_unassigned,
                "fid": firm_with_gid["firm_id"],
                "ae": f"assigned-{firm_with_gid['firm_id'].hex[:4]}@example.com",
                "ue": f"unassigned-{firm_with_gid['firm_id'].hex[:4]}@example.com",
                "ph": hash_password("Correct-Horse-Battery-Staple-42"),
            },
        )
        conn.execute(
            text(
                "INSERT INTO client_assignment (firm_id, user_id, client_id) "
                "VALUES (:fid, :uid, :cid)"
            ),
            {
                "fid": firm_with_gid["firm_id"],
                "uid": staff_assigned,
                "cid": firm_with_gid["client_id"],
            },
        )

    sweep_reminders(date(2026, 8, 13))
    to_emails = sorted({m.to for m in memory_email.sent})
    assert firm_with_gid["admin_email"] in to_emails
    assert any("assigned-" in e for e in to_emails), to_emails
    assert not any("unassigned-" in e for e in to_emails), to_emails
