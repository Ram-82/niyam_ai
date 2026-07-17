"""End-to-end tests for GET /command-center.

Seeds a firm with 2 clients + gstins + snapshots and asserts:

* rows returned for every (client × gstin × return_type) pair.
* score / days_to_due_date / itc_at_risk_paise / blockers_count
  populated correctly from the underlying snapshots + recon summaries.
* NULL score when no snapshot exists (still appears in the list).
* Staff sees only assigned clients; admin sees all.
* Sort order: score ASC (NULLs first), then days_to_due_date ASC.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

import pyotp
import pytest
from sqlalchemy import text

from app.db import owner_engine
from app.engines.validation.gstin import compute_check_digit


def _gstin(base: str) -> str:
    return base + compute_check_digit(base)


PW = "Correct-Horse-Battery-Staple-42"


def _login(client, admin) -> str:
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


def _seed_client_and_gstin(firm_id, name, gstin) -> tuple[uuid.UUID, uuid.UUID]:
    cid, gid = uuid.uuid4(), uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO client (id, firm_id, trade_name) VALUES (:c, :f, :n)"),
            {"c": cid, "f": firm_id, "n": name},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code, scheme) "
                "VALUES (:g, :f, :c, :gs, :sc, 'regular')"
            ),
            {"g": gid, "f": firm_id, "c": cid, "gs": gstin, "sc": gstin[:2]},
        )
    return cid, gid


def _seed_snapshot(
    firm_id, gid, *, period, return_type, score, itc_at_risk_paise, blockers=1
):
    """Directly insert a readiness_snapshot + reconciliation_run so we
    don't have to run the engines end-to-end for a command-center test."""
    snap_id = uuid.uuid4()
    run_id = uuid.uuid4()
    pull_id = uuid.uuid4()
    blockers_json = [{"code": "SUPPLIER_DEFAULT_TOTAL",
                      "description": "x", "owner": "ca",
                      "paise_impact": itc_at_risk_paise}] * blockers
    summary = {
        "matched": {"count": 1, "paise": 100_000},
        "probable": {"count": 0, "paise": 0},
        "supplier_default": {
            "count": 1, "paise": itc_at_risk_paise,
            "top_suppliers": [],
            "with_near_misses": 0,
        },
        "missing_entry": {"count": 0, "paise": 0},
    }
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO gstn_pull (id, firm_id, gstin_profile_id, "
                "return_type, period, raw_payload, source) "
                "VALUES (:id, :f, :g, 'GSTR2B', :p, CAST('{}' AS JSONB), "
                "'json_import')"
            ),
            {"id": pull_id, "f": firm_id, "g": gid, "p": period},
        )
        conn.execute(
            text(
                "INSERT INTO reconciliation_run "
                "(id, firm_id, gstin_profile_id, period, status, "
                "rule_pack_version, gstn_pull_id, summary, "
                "started_at, finished_at) "
                "VALUES (:id, :f, :g, :p, 'completed', '1.0.0', :pull, "
                "CAST(:s AS JSONB), now(), now())"
            ),
            {
                "id": run_id, "f": firm_id, "g": gid, "p": period,
                "pull": pull_id, "s": json.dumps(summary),
            },
        )
        conn.execute(
            text(
                "INSERT INTO readiness_snapshot "
                "(id, firm_id, gstin_profile_id, return_type, period, "
                "score, blockers, arithmetic, rule_pack_version) "
                "VALUES (:id, :f, :g, CAST(:rt AS return_type), :p, :s, "
                "CAST(:b AS JSONB), CAST('{}' AS JSONB), '1.0.0')"
            ),
            {
                "id": snap_id, "f": firm_id, "g": gid,
                "rt": return_type, "p": period, "s": score,
                "b": json.dumps(blockers_json),
            },
        )


def test_command_center_rows_are_populated(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="cc-admin@example.com")
    firm = admin["firm_id"]

    _, gid_a = _seed_client_and_gstin(firm, "Acme", _gstin("29AAAAA0000A1Z"))
    _, gid_b = _seed_client_and_gstin(firm, "Beta", _gstin("27BBBBB1234C2Z"))

    _seed_snapshot(firm, gid_a, period="202606", return_type="GSTR1",
                   score=63, itc_at_risk_paise=43_000_00)
    _seed_snapshot(firm, gid_b, period="202606", return_type="GSTR1",
                   score=90, itc_at_risk_paise=1_000_00)

    access = _login(test_client, admin)
    r = test_client.get(
        "/command-center?period=202606",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["period"] == "202606"
    rows = body["rows"]
    # 2 gstins x 2 return_types = 4 rows minimum.
    assert len(rows) == 4

    by_key = {(r_["gstin"], r_["return_type"]): r_ for r_ in rows}

    acme_g1 = by_key[(_gstin("29AAAAA0000A1Z"), "GSTR1")]
    assert acme_g1["score"] == 63
    assert acme_g1["itc_at_risk_paise"] == 43_000_00
    assert acme_g1["blockers_count"] == 1
    # GSTR1 due 11 July for period 202606
    assert acme_g1["days_to_due_date"] is not None

    # No snapshot yet for GSTR3B → NULL score + zero counters.
    acme_g3b = by_key[(_gstin("29AAAAA0000A1Z"), "GSTR3B")]
    assert acme_g3b["score"] is None
    assert acme_g3b["blockers_count"] == 0
    assert acme_g3b["itc_at_risk_paise"] == 43_000_00  # recon summary shared per period


def test_command_center_sort_score_asc_nulls_first(
    test_client, bootstrap_firm
) -> None:
    admin = bootstrap_firm(admin_email="cc-sort@example.com")
    firm = admin["firm_id"]

    _, gid_low = _seed_client_and_gstin(firm, "LowScore", _gstin("29AAAAA0000A1Z"))
    _, gid_hi = _seed_client_and_gstin(firm, "HighScore", _gstin("27BBBBB1234C2Z"))
    _, gid_null = _seed_client_and_gstin(firm, "NoData", _gstin("07XYZAB9999K9Z"))

    _seed_snapshot(firm, gid_low, period="202606", return_type="GSTR1",
                   score=25, itc_at_risk_paise=100_00)
    _seed_snapshot(firm, gid_hi, period="202606", return_type="GSTR1",
                   score=95, itc_at_risk_paise=100_00)
    # gid_null: no snapshot

    access = _login(test_client, admin)
    r = test_client.get(
        "/command-center?period=202606",
        headers={"Authorization": f"Bearer {access}"},
    )
    rows = r.json()["rows"]

    # First few rows: NULL scores, then ascending. NoData first, then LowScore, then HighScore.
    scores = [r_["score"] for r_ in rows if r_["return_type"] == "GSTR1"]
    assert scores[0] is None
    assert scores[1] == 25
    # HighScore's GSTR1 is somewhere later.
    assert 95 in scores


def test_staff_only_sees_assigned_clients(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="cc-adm@example.com")
    firm = admin["firm_id"]

    # Two clients, only one assigned to the staff user.
    cid_yes, gid_yes = _seed_client_and_gstin(firm, "AssignedCo", _gstin("29AAAAA0000A1Z"))
    _, _ = _seed_client_and_gstin(firm, "OtherCo", _gstin("27BBBBB1234C2Z"))
    _seed_snapshot(firm, gid_yes, period="202606", return_type="GSTR1",
                   score=50, itc_at_risk_paise=0)

    # Create a staff user directly via owner engine (bypass invite flow).
    from app.auth.passwords import hash_password
    from app.auth.totp import generate_secret
    staff_id = uuid.uuid4()
    staff_secret = generate_secret()
    staff_email = "staff@example.com"
    staff_pw = "Correct-Horse-Battery-Staple-99"
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app_user (id, firm_id, email, password_hash, "
                "role, totp_secret, totp_confirmed, is_active) "
                "VALUES (:id, :f, :e, :ph, 'staff', :ts, TRUE, TRUE)"
            ),
            {
                "id": staff_id, "f": firm, "e": staff_email,
                "ph": hash_password(staff_pw), "ts": staff_secret,
            },
        )
        conn.execute(
            text(
                "INSERT INTO client_assignment (firm_id, user_id, client_id) "
                "VALUES (:f, :u, :c)"
            ),
            {"f": firm, "u": staff_id, "c": cid_yes},
        )

    r = test_client.post(
        "/auth/login",
        json={
            "email": staff_email,
            "password": staff_pw,
            "totp_code": pyotp.TOTP(staff_secret).now(),
        },
    )
    assert r.status_code == 200, r.text
    staff_access = r.json()["access_token"]

    r = test_client.get(
        "/command-center?period=202606",
        headers={"Authorization": f"Bearer {staff_access}"},
    )
    rows = r.json()["rows"]
    clients = {r_["client_name"] for r_ in rows}
    assert clients == {"AssignedCo"}


def test_command_center_rls_across_firms(test_client, bootstrap_firm) -> None:
    admin_a = bootstrap_firm(admin_email="a@ex.com")
    admin_b = bootstrap_firm(admin_email="b@ex.com")
    _seed_client_and_gstin(admin_b["firm_id"], "B-Co", _gstin("29AAAAA0000A1Z"))

    access_a = _login(test_client, admin_a)
    r = test_client.get(
        "/command-center?period=202606",
        headers={"Authorization": f"Bearer {access_a}"},
    )
    rows = r.json()["rows"]
    names = {r_["client_name"] for r_ in rows}
    assert "B-Co" not in names
