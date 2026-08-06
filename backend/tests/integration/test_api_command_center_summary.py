"""Command center gains filing_status per row + a firm-wide summary.

Property under test:
- Row's filing_status reflects the current filing_run.status for the
  (gid, period, return_type) triple; null when none exists.
- Summary counts: unfiled/filed roll up correctly across the response.
"""
from __future__ import annotations

import uuid

import pyotp
from sqlalchemy import text

from app.db import owner_engine
from app.engines.validation.gstin import compute_check_digit


GSTIN = "29AAAAA0000A1Z" + compute_check_digit("29AAAAA0000A1Z")
BUYER = "27BBBBB1234C2Z" + compute_check_digit("27BBBBB1234C2Z")


def _login(client, admin) -> str:
    r = client.post(
        "/auth/login",
        json={
            "email": admin["email"],
            "password": admin["password"],
            "totp_code": pyotp.TOTP(admin["totp_secret"]).now(),
        },
    )
    assert r.status_code == 200
    return r.json()["access_token"]


def _seed(admin_email, bootstrap_firm, period="202607"):
    admin = bootstrap_firm(admin_email=admin_email)
    fid = admin["firm_id"]
    cid, gid = uuid.uuid4(), uuid.uuid4()
    with owner_engine.begin() as c:
        c.execute(
            text("INSERT INTO client (id, firm_id, trade_name) VALUES (:c,:f,'CC')"),
            {"c": cid, "f": fid},
        )
        c.execute(
            text(
                "INSERT INTO gstin_profile (id, firm_id, client_id, gstin, "
                "state_code, scheme) VALUES (:g,:f,:c,:gs,'29','regular')"
            ),
            {"g": gid, "f": fid, "c": cid, "gs": GSTIN},
        )
        # A sale so generate_filing has something to emit.
        c.execute(
            text(
                """
                INSERT INTO invoice (
                  firm_id, gstin_profile_id, source, direction,
                  invoice_number, invoice_date, counterparty_gstin,
                  taxable_value_paise, cgst_paise, sgst_paise, igst_paise,
                  total_paise, content_hash
                ) VALUES (
                  :f,:g,'csv_import','sale','S-1', DATE '2026-07-15', :cp,
                  100000, 0, 0, 12000, 112000, 'h-S-1'
                )
                """
            ),
            {"f": fid, "g": gid, "cp": BUYER},
        )
    return admin, gid


def test_command_center_surfaces_filing_status_and_summary(
    test_client, bootstrap_firm
) -> None:
    admin, gid = _seed("cc@example.com", bootstrap_firm)
    access = _login(test_client, admin)
    hdrs = {"Authorization": f"Bearer {access}"}
    period = "202607"

    # No filing yet — filing_status is null; summary counts both returns
    # (GSTR1 + GSTR3B) as unfiled.
    r = test_client.get(f"/command-center?period={period}", headers=hdrs)
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["total_rows"] == 2
    assert body["summary"]["unfiled_count"] == 2
    assert body["summary"]["filed_count"] == 0
    for row in body["rows"]:
        assert row["filing_status"] is None

    # Generate + approve + mark-filed the GSTR1.
    r = test_client.post(
        "/filings/generate",
        headers=hdrs,
        json={"gstin_profile_id": str(gid), "period": period, "return_type": "GSTR1"},
    )
    assert r.status_code == 200
    filing_id = r.json()["id"]
    assert test_client.post(f"/filings/{filing_id}/approve", headers=hdrs).status_code == 200
    r = test_client.post(
        f"/filings/{filing_id}/mark-filed",
        headers=hdrs,
        json={"arn": "AA010725012345Z"},
    )
    assert r.status_code == 200

    # Command center now shows GSTR1 as filed, GSTR3B still unfiled.
    r = test_client.get(f"/command-center?period={period}", headers=hdrs)
    body = r.json()
    assert body["summary"]["filed_count"] == 1
    assert body["summary"]["unfiled_count"] == 1
    gstr1_row = next(x for x in body["rows"] if x["return_type"] == "GSTR1")
    gstr3b_row = next(x for x in body["rows"] if x["return_type"] == "GSTR3B")
    assert gstr1_row["filing_status"] == "filed"
    assert gstr3b_row["filing_status"] is None


def test_command_center_summary_shape(test_client, bootstrap_firm) -> None:
    admin, _ = _seed("cs@example.com", bootstrap_firm)
    access = _login(test_client, admin)
    r = test_client.get(
        "/command-center?period=202607",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200
    s = r.json()["summary"]
    for key in (
        "total_rows",
        "unfiled_count",
        "filed_count",
        "total_itc_at_risk_paise",
        "high_risk_count",
        "due_soon_count",
    ):
        assert key in s, f"summary missing {key}"
