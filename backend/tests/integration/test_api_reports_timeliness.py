"""GET /reports/timeliness — on-time vs late filings per month per return type.

The endpoint reads filing_run + audit_log (mark-filed timestamp) and
compares filed_on to the statutory due date from the firm's active rule
pack. This suite proves the aggregation across the four state
combinations that matter: no filings, all on-time, mix of on-time/late,
and multi-return-type per-month buckets."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

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


def _add_gstin(firm_id, gstin: str, state_code: str) -> uuid.UUID:
    cid, gid = uuid.uuid4(), uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name, language) "
                "VALUES (:id, :fid, :n, 'en')"
            ),
            {"id": cid, "fid": firm_id, "n": f"Client-{gstin[-4:]}"},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code, scheme) "
                "VALUES (:id, :fid, :cid, :g, :sc, 'regular'::gst_scheme)"
            ),
            {"id": gid, "fid": firm_id, "cid": cid, "g": gstin, "sc": state_code},
        )
    return gid


def _add_filed_run(
    firm_id, gstin_profile_id, period: str, return_type: str, filed_at: datetime, user_id
) -> uuid.UUID:
    """Insert a filing_run with status='filed' + the matching audit_log
    row that the endpoint keys off."""
    fid = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO filing_run "
                "(id, firm_id, gstin_profile_id, period, return_type, status, "
                " payload, rule_pack_version) "
                "VALUES (:id, :fid, :g, :p, CAST(:rt AS return_type), 'filed'::filing_status, "
                "        '{}'::jsonb, 'v1')"
            ),
            {"id": fid, "fid": firm_id, "g": gstin_profile_id, "p": period, "rt": return_type},
        )
        conn.execute(
            text(
                "INSERT INTO audit_log (id, firm_id, user_id, action, entity_type, "
                "entity_id, diff, at) "
                "VALUES (gen_random_uuid(), :fid, :uid, 'filing.marked_filed', 'filing_run', "
                "        :fr, '{}'::jsonb, :at)"
            ),
            {"fid": firm_id, "uid": user_id, "fr": fid, "at": filed_at},
        )
    return fid


def _kolkata(y: int, m: int, d: int, hour: int = 10) -> datetime:
    """Naive local IST wall-clock as UTC — endpoint converts back to IST."""
    ist_offset = timedelta(hours=5, minutes=30)
    return datetime(y, m, d, hour, 0, tzinfo=timezone(ist_offset)).astimezone(timezone.utc)


def test_empty_returns_zero_totals_and_full_window(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"tl0-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)
    r = test_client.get(
        "/reports/timeliness?period_from=202601&period_to=202603",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period_from"] == "202601"
    assert body["period_to"] == "202603"
    assert body["total_filed"] == 0
    assert body["total_on_time"] == 0
    assert len(body["months"]) == 3
    assert [m["period"] for m in body["months"]] == ["202601", "202602", "202603"]
    for m in body["months"]:
        assert m["gstr1_filed"] == 0 and m["gstr1_on_time"] == 0
        assert m["gstr3b_filed"] == 0 and m["gstr3b_on_time"] == 0


def test_on_time_vs_late_classification(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"tl1-{uuid.uuid4().hex[:6]}@example.com")
    firm_id = admin["firm_id"]
    user_id = admin["user_id"]
    g = _add_gstin(firm_id, _mk_gstin("29AAAAA0000A1Z"), "29")

    # Period 202601 GSTR-1 due 2026-02-11.
    _add_filed_run(firm_id, g, "202601", "GSTR1", _kolkata(2026, 2, 5), user_id)   # on-time
    _add_filed_run(firm_id, g, "202602", "GSTR1", _kolkata(2026, 3, 15), user_id)  # late
    # Period 202601 GSTR-3B due 2026-02-20.
    _add_filed_run(firm_id, g, "202601", "GSTR3B", _kolkata(2026, 2, 20), user_id) # boundary on-time
    _add_filed_run(firm_id, g, "202602", "GSTR3B", _kolkata(2026, 3, 21), user_id) # 1-day late

    tok = _bearer(test_client, admin)
    r = test_client.get(
        "/reports/timeliness?period_from=202601&period_to=202602",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_filed"] == 4
    assert body["total_on_time"] == 2
    m1, m2 = body["months"]
    assert m1["period"] == "202601"
    assert m1["gstr1_filed"] == 1 and m1["gstr1_on_time"] == 1
    assert m1["gstr3b_filed"] == 1 and m1["gstr3b_on_time"] == 1
    assert m2["period"] == "202602"
    assert m2["gstr1_filed"] == 1 and m2["gstr1_on_time"] == 0
    assert m2["gstr3b_filed"] == 1 and m2["gstr3b_on_time"] == 0


def test_multiple_gstins_aggregate_per_period(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"tl2-{uuid.uuid4().hex[:6]}@example.com")
    firm_id = admin["firm_id"]
    user_id = admin["user_id"]
    g1 = _add_gstin(firm_id, _mk_gstin("29BBBBB0000B1Z"), "29")
    g2 = _add_gstin(firm_id, _mk_gstin("27CCCCC0000C1Z"), "27")
    # Same period, both on-time.
    _add_filed_run(firm_id, g1, "202603", "GSTR1", _kolkata(2026, 4, 8), user_id)
    _add_filed_run(firm_id, g2, "202603", "GSTR1", _kolkata(2026, 4, 10), user_id)
    # Same period, one late.
    _add_filed_run(firm_id, g1, "202603", "GSTR3B", _kolkata(2026, 4, 19), user_id)
    _add_filed_run(firm_id, g2, "202603", "GSTR3B", _kolkata(2026, 4, 22), user_id)

    tok = _bearer(test_client, admin)
    r = test_client.get(
        "/reports/timeliness?period_from=202603&period_to=202603",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["months"]) == 1
    m = body["months"][0]
    assert m["gstr1_filed"] == 2 and m["gstr1_on_time"] == 2
    assert m["gstr3b_filed"] == 2 and m["gstr3b_on_time"] == 1


def test_defaults_to_trailing_12_months_when_window_omitted(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"tl3-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)
    r = test_client.get("/reports/timeliness", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["months"]) == 12
    # First and last periods span 12 months inclusive.
    fy, fm = int(body["period_from"][:4]), int(body["period_from"][4:])
    ty, tm = int(body["period_to"][:4]), int(body["period_to"][4:])
    diff_months = (ty - fy) * 12 + (tm - fm)
    assert diff_months == 11


def test_period_from_after_period_to_returns_400(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"tl4-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)
    r = test_client.get(
        "/reports/timeliness?period_from=202606&period_to=202601",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 400
    assert "period_from" in r.json()["detail"]


def test_bad_period_format_422(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"tl5-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)
    r = test_client.get(
        "/reports/timeliness?period_from=2026-01&period_to=202603",
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert r.status_code == 422
