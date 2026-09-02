"""GET /filings — firm-wide filing list used by the v2 picker."""
from __future__ import annotations

import uuid

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


def _seed_filing(
    firm_id: uuid.UUID,
    *,
    trade_name: str,
    status: str,
    period: str = "202607",
    return_type: str = "GSTR3B",
) -> tuple[uuid.UUID, uuid.UUID]:
    client_id = uuid.uuid4()
    gid = uuid.uuid4()
    filing_id = uuid.uuid4()
    digits = f"{uuid.uuid4().int % 10000:04d}"
    gstin = f"29ABCDE{digits}F1Z5"
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO client (id, firm_id, trade_name) VALUES (:c, :f, :n)"),
            {"c": client_id, "f": firm_id, "n": trade_name},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code, scheme) "
                "VALUES (:g, :f, :c, :gstin, '29', 'regular')"
            ),
            {"g": gid, "f": firm_id, "c": client_id, "gstin": gstin},
        )
        conn.execute(
            text(
                """
                INSERT INTO filing_run (
                    id, firm_id, gstin_profile_id, period, return_type,
                    status, rule_pack_version, payload
                ) VALUES (
                    :id, :f, :g, :p, :rt,
                    :st, 'v1.0.0', '{}'::jsonb
                )
                """
            ),
            {
                "id": filing_id, "f": firm_id, "g": gid,
                "p": period, "rt": return_type, "st": status,
            },
        )
    return filing_id, gid


def test_list_empty_firm(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"fl-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)
    r = test_client.get("/filings", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert r.json() == []


def test_list_returns_enriched_rows(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"f2-{uuid.uuid4().hex[:6]}@example.com")
    firm_id = admin["firm_id"]
    _seed_filing(firm_id, trade_name="Acme Traders", status="draft")

    tok = _bearer(test_client, admin)
    r = test_client.get("/filings", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["client_name"] == "Acme Traders"
    assert row["gstin"].startswith("29")
    assert row["return_type"] == "GSTR3B"
    assert row["period"] == "202607"
    assert row["status"] == "draft"
    # id is a stringified UUID; picker uses it in the ?id= URL.
    assert uuid.UUID(row["id"])


def test_list_filters_by_status(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"f3-{uuid.uuid4().hex[:6]}@example.com")
    firm_id = admin["firm_id"]
    _seed_filing(firm_id, trade_name="Draft Co", status="draft", period="202607")
    _seed_filing(firm_id, trade_name="Filed Co", status="filed", period="202606")

    tok = _bearer(test_client, admin)
    r = test_client.get(
        "/filings?status=filed", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["client_name"] == "Filed Co"
    assert rows[0]["status"] == "filed"


def test_list_rejects_bad_status(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"f4-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)
    r = test_client.get(
        "/filings?status=bogus", headers={"Authorization": f"Bearer {tok}"}
    )
    assert r.status_code == 422


def test_list_rls_isolates(test_client, bootstrap_firm) -> None:
    admin_a = bootstrap_firm(firm_name="A", admin_email=f"fa-{uuid.uuid4().hex[:6]}@example.com")
    admin_b = bootstrap_firm(firm_name="B", admin_email=f"fb-{uuid.uuid4().hex[:6]}@example.com")
    _seed_filing(admin_a["firm_id"], trade_name="A-Co", status="draft")
    _seed_filing(admin_b["firm_id"], trade_name="B-Co", status="draft")

    tok_a = _bearer(test_client, admin_a)
    r = test_client.get("/filings", headers={"Authorization": f"Bearer {tok_a}"})
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["client_name"] == "A-Co"


def test_list_requires_auth(test_client) -> None:
    r = test_client.get("/filings")
    assert r.status_code == 401
