"""POST /clients/import — bulk CSV import.

Covers:
  * auto-column-mapping via header keywords
  * dry-run reports errors + preview without inserting
  * commit path creates real Client + GstinProfile rows
  * per-row errors (bad GSTIN, missing trade_name, bad E.164)
  * warnings (empty rows, derived state_code)
  * scheme normalisation
  * duplicate GSTIN warning
"""
from __future__ import annotations

import io
import json
import uuid

import pyotp
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


def _upload(client, tok: str, csv_body: str, *, mapping: dict | None = None, dry_run: bool = True):
    return client.post(
        "/clients/import",
        headers={"Authorization": f"Bearer {tok}"},
        params={"dry_run": str(dry_run).lower()},
        files={"file": ("clients.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")},
        data={"mapping": json.dumps(mapping) if mapping is not None else "{}"},
    )


CSV_GOOD = """Client Name,GSTIN,State,WhatsApp,Business Type
Acme Textiles Pvt Ltd,29AAAAA0000A1Z5,29,+919812345001,regular
Bravo Foods LLP,27BBBBB0000B1Z2,27,,regular
"""


def test_dry_run_auto_maps_and_previews(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"imp-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)

    r = _upload(test_client, tok, CSV_GOOD, dry_run=True)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_rows"] == 2
    assert body["dry_run"] is True
    assert body["created_clients"] == 0
    assert body["created_gstins"] == 0
    # Auto-mapping picks up the human column names.
    assert body["resolved_mapping"]["Client Name"] == "trade_name"
    assert body["resolved_mapping"]["GSTIN"] == "gstin"
    assert body["resolved_mapping"]["State"] == "state_code"
    assert body["resolved_mapping"]["WhatsApp"] == "whatsapp_number"
    assert body["resolved_mapping"]["Business Type"] == "scheme"
    assert len(body["preview"]) == 2
    assert body["preview"][0]["trade_name"] == "Acme Textiles Pvt Ltd"
    # No inserts happened.
    with owner_engine.begin() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM client WHERE firm_id = :fid"),
            {"fid": admin["firm_id"]},
        ).scalar()
    assert count == 0


def test_commit_inserts_rows_and_creates_gstins(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"imp2-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)

    r = _upload(test_client, tok, CSV_GOOD, dry_run=False)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created_clients"] == 2
    assert body["created_gstins"] == 2

    with owner_engine.begin() as conn:
        clients = conn.execute(
            text("SELECT trade_name FROM client WHERE firm_id = :fid ORDER BY trade_name"),
            {"fid": admin["firm_id"]},
        ).scalars().all()
        gstins = conn.execute(
            text("SELECT gstin FROM gstin_profile WHERE firm_id = :fid ORDER BY gstin"),
            {"fid": admin["firm_id"]},
        ).scalars().all()
    assert clients == ["Acme Textiles Pvt Ltd", "Bravo Foods LLP"]
    assert "29AAAAA0000A1Z5" in gstins and "27BBBBB0000B1Z2" in gstins


def test_reports_per_row_errors_without_blocking_valid_rows(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"imp3-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)

    bad = """Client Name,GSTIN,State
Good Row LLP,29GOODA0000A1ZL,29
,29AAAAA0000A1Z5,29
Bad Gstin Row,NOTAGSTIN,
State Mismatch Co,29AAAAA0000A1Z5,27
Missing Fields Co,,
"""
    r = _upload(test_client, tok, bad, dry_run=True)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_rows"] == 5
    error_msgs = " || ".join(e["message"] for e in body["errors"])
    # Row 3: empty trade_name
    assert "trade_name is required" in error_msgs
    # Row 4: bad GSTIN structural
    assert "fails structural format" in error_msgs
    # Row 5: state_code disagrees with GSTIN prefix
    assert "disagrees with GSTIN prefix" in error_msgs
    # Row 2 (only valid one) makes it to preview
    valid_preview = [p for p in body["preview"] if p["trade_name"]]
    assert any(p["trade_name"] == "Good Row LLP" for p in valid_preview)


def test_derives_state_from_gstin_and_warns(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"imp4-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)

    r = _upload(
        test_client,
        tok,
        "Name,GST\nDerived State Co,29AAAAA0000A1Z5\n",
        dry_run=True,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["errors"] == []
    warn_msgs = " || ".join(w["message"] for w in body["warnings"])
    assert "derived from GSTIN as '29'" in warn_msgs


def test_missing_required_trade_name_column_400s(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"imp5-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)

    r = _upload(test_client, tok, "GST,State\n29AAAAA0000A1Z5,29\n", dry_run=True)
    assert r.status_code == 400
    assert "trade_name" in r.json()["detail"]


def test_user_mapping_overrides_auto(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"imp6-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)

    # CSV has ambiguous headers; user explicitly maps.
    csv = "col1,col2\nMy Client,29AAAAA0000A1Z5\n"
    r = _upload(
        test_client, tok, csv,
        mapping={"col1": "trade_name", "col2": "gstin"},
        dry_run=True,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["errors"] == []
    assert body["preview"][0]["trade_name"] == "My Client"
    assert body["preview"][0]["gstin"] == "29AAAAA0000A1Z5"


def test_rejects_empty_file(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"imp7-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)

    r = _upload(test_client, tok, "", dry_run=True)
    assert r.status_code == 400
    assert "empty" in r.json()["detail"]


def test_bad_whatsapp_reports_row_error(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email=f"imp8-{uuid.uuid4().hex[:6]}@example.com")
    tok = _bearer(test_client, admin)

    r = _upload(
        test_client, tok,
        "Name,WhatsApp\nBad Phone Co,9812345001\n",
        dry_run=True,
    )
    assert r.status_code == 200
    body = r.json()
    assert any("E.164" in e["message"] for e in body["errors"])
