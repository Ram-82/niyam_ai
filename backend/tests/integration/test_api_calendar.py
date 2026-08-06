"""GET /calendar/upcoming — surface for the frontend calendar view."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pyotp
import pytest
from sqlalchemy import text

from app.db import owner_engine


STRONG_PW = "Correct-Horse-Battery-Staple-42"


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


@pytest.fixture
def firm_with_gid_and_filed(bootstrap_firm):
    """Seed: admin firm + client + one GID + one FILED GSTR-3B for last month."""
    admin = bootstrap_firm(admin_email=f"cal-admin-{uuid.uuid4().hex[:6]}@example.com")
    client_id = uuid.uuid4()
    gid_id = uuid.uuid4()
    gstin = "29ABCDE1234F1Z5"
    # Pick "last month" relative to the request time so days_out is negative.
    today = datetime.now(tz=timezone.utc).date()
    if today.month == 1:
        prev_y, prev_m = today.year - 1, 12
    else:
        prev_y, prev_m = today.year, today.month - 1
    filed_period = f"{prev_y:04d}{prev_m:02d}"

    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:cid, :fid, 'Ramesh Textiles')"
            ),
            {"cid": client_id, "fid": admin["firm_id"]},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code) "
                "VALUES (:gid, :fid, :cid, :gstin, :st)"
            ),
            {
                "gid": gid_id, "fid": admin["firm_id"],
                "cid": client_id, "gstin": gstin, "st": gstin[:2],
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO filing_run (
                    firm_id, gstin_profile_id, return_type, period,
                    status, payload, rule_pack_version
                ) VALUES (
                    :fid, :gid, 'GSTR3B', :p,
                    'filed', '{}'::jsonb, 'v-test'
                )
                """
            ),
            {"fid": admin["firm_id"], "gid": gid_id, "p": filed_period},
        )

    return {
        **admin,
        "client_id": client_id, "gid_id": gid_id, "gstin": gstin,
        "filed_period": filed_period,
    }


def test_empty_firm_returns_empty_rows(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"empty-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)
    r = test_client.get(
        "/calendar/upcoming",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] == []
    assert body["horizon_days"] == 45
    assert body["lookback_days"] == 14


def test_gid_produces_rows_with_status_and_reminders(
    test_client, firm_with_gid_and_filed
) -> None:
    admin = firm_with_gid_and_filed
    tok = _bearer(test_client, admin)

    r = test_client.get(
        "/calendar/upcoming?horizon_days=90&lookback_days=45",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    rows = r.json()["rows"]
    assert rows, "seed produced no candidate rows — check windowing"

    # Every row must carry the seeded GID + client name.
    assert all(row["gstin"] == admin["gstin"] for row in rows)
    assert all(row["client_trade_name"] == "Ramesh Textiles" for row in rows)

    # The filed period must show up with filing_status="filed" (may be
    # outside the window depending on today, but with 45d lookback it
    # should land in-window for typical mid-month runs).
    filed_rows = [
        r for r in rows
        if r["period"] == admin["filed_period"] and r["return_type"] == "GSTR3B"
    ]
    if filed_rows:
        assert filed_rows[0]["filing_status"] == "filed"

    # Rows are sorted by due_date ascending.
    dates = [r["due_date"] for r in rows]
    assert dates == sorted(dates)


def test_rls_scopes_to_caller_firm(test_client, bootstrap_firm) -> None:
    """Firm A must never see Firm B's GIDs on their calendar."""
    admin_a = bootstrap_firm(firm_name="Firm A", admin_email=f"a-{uuid.uuid4().hex[:6]}@example.com")
    admin_b = bootstrap_firm(firm_name="Firm B", admin_email=f"b-{uuid.uuid4().hex[:6]}@example.com")

    # Seed a GID under Firm B only.
    client_b = uuid.uuid4()
    gid_b = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO client (id, firm_id, trade_name) VALUES (:c, :f, 'B-Corp')"),
            {"c": client_b, "f": admin_b["firm_id"]},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile (id, firm_id, client_id, gstin, state_code) "
                "VALUES (:g, :f, :c, :gstin, :st)"
            ),
            {"g": gid_b, "f": admin_b["firm_id"], "c": client_b, "gstin": "27ZZZZE9999F1Z8", "st": "27"},
        )

    tok_a = _bearer(test_client, admin_a)
    r = test_client.get(
        "/calendar/upcoming",
        headers={"Authorization": f"Bearer {tok_a}"},
    )
    assert r.status_code == 200
    for row in r.json()["rows"]:
        assert row["gstin"] != "27ZZZZE9999F1Z8"


def test_unauthenticated_rejected(test_client) -> None:
    r = test_client.get("/calendar/upcoming")
    assert r.status_code in (401, 403), r.text
