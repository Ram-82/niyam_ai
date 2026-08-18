"""GET /firm/health-summary + GET /firm/recent-activity.

These are the two aggregate endpoints the v2 dashboard depends on.
Tests cover: empty-firm shape, snapshot rollup, client bucketing,
audit-log enrichment, RLS isolation, and auth enforcement.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pyotp
import pytest
from sqlalchemy import text

from app.db import owner_engine


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


def _seed_client_with_snapshot(
    firm_id: uuid.UUID,
    *,
    trade_name: str,
    score: int | None,
    blockers: list[dict] | None = None,
    scheme: str = "regular",
    gstin: str | None = None,
    mark_filed: bool = False,
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert client + gstin_profile + latest readiness snapshot.

    Returns (client_id, gstin_profile_id). Uses owner_engine to bypass
    RLS since the test is setting up seed state, not exercising it."""
    client_id = uuid.uuid4()
    gid = uuid.uuid4()
    # GSTIN format: 2-digit state + 5 letters + 4 digits + 1 letter + 1
    # digit + 'Z' + 1 alnum. Use uuid4 int for the 4 digits to keep it
    # unique across seed calls without a shared counter.
    if gstin is None:
        digits = f"{uuid.uuid4().int % 10000:04d}"
        gstin = f"29ABCDE{digits}F1Z5"
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:cid, :fid, :name)"
            ),
            {"cid": client_id, "fid": firm_id, "name": trade_name},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code, scheme) "
                "VALUES (:gid, :fid, :cid, :gstin, :state, :scheme)"
            ),
            {
                "gid": gid,
                "fid": firm_id,
                "cid": client_id,
                "gstin": gstin,
                "state": gstin[:2],
                "scheme": scheme,
            },
        )
        if score is not None:
            conn.execute(
                text(
                    """
                    INSERT INTO readiness_snapshot (
                        id, firm_id, gstin_profile_id, return_type,
                        period, score, blockers, arithmetic,
                        rule_pack_version, computed_at
                    ) VALUES (
                        :id, :fid, :gid, 'GSTR3B',
                        '202607', :score, CAST(:blockers AS JSONB),
                        '{}'::jsonb, 'v1.0.0', NOW()
                    )
                    """
                ),
                {
                    "id": uuid.uuid4(),
                    "fid": firm_id,
                    "gid": gid,
                    "score": score,
                    "blockers": json.dumps(blockers or []),
                },
            )
        if mark_filed:
            conn.execute(
                text(
                    """
                    INSERT INTO filing_run (
                        id, firm_id, gstin_profile_id, period, return_type,
                        status, rule_pack_version, payload
                    ) VALUES (
                        :id, :fid, :gid, '202607', 'GSTR3B',
                        'filed', 'v1.0.0', '{}'::jsonb
                    )
                    """
                ),
                {"id": uuid.uuid4(), "fid": firm_id, "gid": gid},
            )
    return client_id, gid


# ---------------------------------------------------------------------------
# /firm/health-summary
# ---------------------------------------------------------------------------


def test_health_summary_empty_firm(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"h1-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)
    r = test_client.get(
        "/firm/health-summary", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["score"] is None
    assert body["prev_score"] is None
    assert body["active_clients_count"] == 0
    assert body["distribution"] == {
        "healthy": 0, "due_soon": 0, "overdue_blocked": 0,
    }


def test_health_summary_buckets_clients(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"h2-{uuid.uuid4().hex[:6]}@example.com")
    firm_id = admin["firm_id"]

    # All three seed the latest scored period as already 'filed' so the
    # due-soon / overdue signals fire only from score + blockers, not
    # from an unfiled current-period filing.
    _seed_client_with_snapshot(
        firm_id, trade_name="Healthy Co", score=90, mark_filed=True,
    )
    _seed_client_with_snapshot(
        firm_id,
        trade_name="Blocked Co",
        score=85,
        blockers=[{"owner": "client", "kind": "missing_doc"}],
        mark_filed=True,
    )
    _seed_client_with_snapshot(
        firm_id, trade_name="Critical Co", score=42, mark_filed=True,
    )

    tok = _bearer(test_client, admin)
    r = test_client.get(
        "/firm/health-summary", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active_clients_count"] == 3
    # Mean of 90, 85, 42 = 72.33 → 72
    assert body["score"] == 72
    dist = body["distribution"]
    assert dist["healthy"] == 1           # Healthy Co
    assert dist["overdue_blocked"] == 2   # Blocked Co (blockers) + Critical Co (<60)
    assert dist["due_soon"] == 0
    assert body["last_computed_at"] is not None


def test_health_summary_rls_isolates_firms(test_client, bootstrap_firm) -> None:
    admin_a = bootstrap_firm(
        firm_name="Firm A",
        admin_email=f"ha-{uuid.uuid4().hex[:6]}@example.com",
    )
    admin_b = bootstrap_firm(
        firm_name="Firm B",
        admin_email=f"hb-{uuid.uuid4().hex[:6]}@example.com",
    )
    _seed_client_with_snapshot(admin_a["firm_id"], trade_name="A-Co", score=95)
    _seed_client_with_snapshot(admin_b["firm_id"], trade_name="B-Co", score=45)

    tok_a = _bearer(test_client, admin_a)
    r = test_client.get(
        "/firm/health-summary", headers={"Authorization": f"Bearer {tok_a}"}
    )
    body = r.json()
    assert body["active_clients_count"] == 1
    assert body["score"] == 95  # Only A-Co visible


def test_health_summary_requires_auth(test_client) -> None:
    r = test_client.get("/firm/health-summary")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# /firm/recent-activity
# ---------------------------------------------------------------------------


def test_recent_activity_empty_firm(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"a1-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)
    r = test_client.get(
        "/firm/recent-activity", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 200, r.text
    # The bootstrap admin's login itself may or may not audit; either
    # way the response is a list.
    assert isinstance(r.json(), list)


def test_recent_activity_enriches_filing_run(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"a2-{uuid.uuid4().hex[:6]}@example.com")
    firm_id = admin["firm_id"]
    _, gid = _seed_client_with_snapshot(
        firm_id, trade_name="Acme Widgets Pvt Ltd", score=80,
    )
    # Insert a filing_run + matching audit_log row.
    filing_id = uuid.uuid4()
    audit_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO filing_run (
                    id, firm_id, gstin_profile_id, period, return_type,
                    status, rule_pack_version, payload
                ) VALUES (
                    :id, :fid, :gid, '202607', 'GSTR3B',
                    'filed', 'v1.0.0', '{}'::jsonb
                )
                """
            ),
            {"id": filing_id, "fid": firm_id, "gid": gid},
        )
        conn.execute(
            text(
                """
                INSERT INTO audit_log (
                    id, firm_id, user_id, action, entity_type,
                    entity_id, diff, at
                ) VALUES (
                    :id, :fid, :uid, 'filing.marked_filed', 'filing_run',
                    :eid, '{"note": "test"}'::jsonb, NOW()
                )
                """
            ),
            {
                "id": audit_id,
                "fid": firm_id,
                "uid": admin["user_id"],
                "eid": filing_id,
            },
        )

    tok = _bearer(test_client, admin)
    r = test_client.get(
        "/firm/recent-activity?limit=20",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    items = r.json()
    # Find our seeded item.
    seeded = [i for i in items if i["action"] == "filing.marked_filed"]
    assert len(seeded) == 1
    it = seeded[0]
    assert it["tone"] == "success"
    assert it["icon"] == "check"
    assert it["title"].startswith("Filing")
    assert it["subtitle"] is not None
    assert "Acme Widgets Pvt Ltd" in it["subtitle"]
    assert "GSTR3B" in it["subtitle"]
    assert "Jul 2026" in it["subtitle"]


def test_recent_activity_rls_isolates(test_client, bootstrap_firm) -> None:
    admin_a = bootstrap_firm(
        firm_name="Firm A",
        admin_email=f"ra-{uuid.uuid4().hex[:6]}@example.com",
    )
    admin_b = bootstrap_firm(
        firm_name="Firm B",
        admin_email=f"rb-{uuid.uuid4().hex[:6]}@example.com",
    )
    # Insert an audit row for firm B.
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO audit_log (
                    id, firm_id, user_id, action, entity_type,
                    entity_id, diff, at
                ) VALUES (
                    :id, :fid, :uid, 'firm.settings_updated', 'ca_firm',
                    :eid, '{}'::jsonb, NOW()
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "fid": admin_b["firm_id"],
                "uid": admin_b["user_id"],
                "eid": admin_b["firm_id"],
            },
        )

    tok_a = _bearer(test_client, admin_a)
    r = test_client.get(
        "/firm/recent-activity", headers={"Authorization": f"Bearer {tok_a}"}
    )
    assert r.status_code == 200
    # Firm A must not see Firm B's audit row.
    for item in r.json():
        assert item["action"] != "firm.settings_updated"


def test_recent_activity_requires_auth(test_client) -> None:
    r = test_client.get("/firm/recent-activity")
    assert r.status_code == 401
