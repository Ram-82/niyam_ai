"""Filing state machine: draft -> approved -> filed with an unlock escape.

Property under test:
- Only the three whitelisted transitions succeed.
- Regenerating a non-draft raises 409 (FilingLocked; already covered in
  the generators test, re-asserted here for the state-machine story).
- Every transition writes an audit row with the correct action.
- ``filed`` is terminal — no approve/unlock/regenerate accepted.
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
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _seed(admin_email, bootstrap_firm):
    admin = bootstrap_firm(admin_email=admin_email)
    fid = admin["firm_id"]
    cid, gid = uuid.uuid4(), uuid.uuid4()
    with owner_engine.begin() as c:
        c.execute(
            text("INSERT INTO client (id, firm_id, trade_name) VALUES (:c,:f,'T')"),
            {"c": cid, "f": fid},
        )
        c.execute(
            text(
                "INSERT INTO gstin_profile (id, firm_id, client_id, gstin, "
                "state_code, scheme) VALUES (:g,:f,:c,:gs,'29','regular')"
            ),
            {"g": gid, "f": fid, "c": cid, "gs": GSTIN},
        )
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


def _generate(client, access, gid):
    r = client.post(
        "/filings/generate",
        headers={"Authorization": f"Bearer {access}"},
        json={"gstin_profile_id": str(gid), "period": "202607", "return_type": "GSTR1"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _auth_headers(access):
    return {"Authorization": f"Bearer {access}"}


def test_happy_path_draft_approved_filed(test_client, bootstrap_firm) -> None:
    admin, gid = _seed("hp@example.com", bootstrap_firm)
    access = _login(test_client, admin)
    fid = _generate(test_client, access, gid)["id"]

    r = test_client.post(f"/filings/{fid}/approve", headers=_auth_headers(access))
    assert r.status_code == 200
    assert r.json()["status"] == "approved"

    r = test_client.post(
        f"/filings/{fid}/mark-filed",
        headers=_auth_headers(access),
        json={"arn": "AA010725012345Z"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "filed"

    # Audit trail records all three lifecycle events for this filing_run.
    r = test_client.get(
        f"/audit-log?entity_type=filing_run&entity_id={fid}",
        headers=_auth_headers(access),
    )
    actions = [row["action"] for row in r.json()]
    assert "filing.generated" in actions
    assert "filing.approved" in actions
    assert "filing.filed" in actions


def test_regenerate_blocked_when_approved(test_client, bootstrap_firm) -> None:
    admin, gid = _seed("rg@example.com", bootstrap_firm)
    access = _login(test_client, admin)
    fid = _generate(test_client, access, gid)["id"]
    r = test_client.post(f"/filings/{fid}/approve", headers=_auth_headers(access))
    assert r.status_code == 200

    r = test_client.post(
        "/filings/generate",
        headers=_auth_headers(access),
        json={"gstin_profile_id": str(gid), "period": "202607", "return_type": "GSTR1"},
    )
    assert r.status_code == 409, r.text


def test_unlock_returns_to_draft(test_client, bootstrap_firm) -> None:
    admin, gid = _seed("ul@example.com", bootstrap_firm)
    access = _login(test_client, admin)
    fid = _generate(test_client, access, gid)["id"]
    test_client.post(f"/filings/{fid}/approve", headers=_auth_headers(access))

    r = test_client.post(f"/filings/{fid}/unlock", headers=_auth_headers(access))
    assert r.status_code == 200
    assert r.json()["status"] == "draft"

    # Regenerate should now succeed again.
    r = test_client.post(
        "/filings/generate",
        headers=_auth_headers(access),
        json={"gstin_profile_id": str(gid), "period": "202607", "return_type": "GSTR1"},
    )
    assert r.status_code == 200


def test_mark_filed_on_draft_rejected(test_client, bootstrap_firm) -> None:
    admin, gid = _seed("mf@example.com", bootstrap_firm)
    access = _login(test_client, admin)
    fid = _generate(test_client, access, gid)["id"]

    r = test_client.post(
        f"/filings/{fid}/mark-filed",
        headers=_auth_headers(access),
        json={"arn": None},
    )
    assert r.status_code == 409, r.text


def test_filed_is_terminal(test_client, bootstrap_firm) -> None:
    admin, gid = _seed("t@example.com", bootstrap_firm)
    access = _login(test_client, admin)
    fid = _generate(test_client, access, gid)["id"]
    test_client.post(f"/filings/{fid}/approve", headers=_auth_headers(access))
    test_client.post(
        f"/filings/{fid}/mark-filed",
        headers=_auth_headers(access),
        json={"arn": "ARN-X"},
    )
    # Every subsequent transition is 409.
    for path in ["approve", "unlock", "mark-filed"]:
        r = test_client.post(
            f"/filings/{fid}/{path}",
            headers=_auth_headers(access),
            json={"arn": None} if path == "mark-filed" else None,
        )
        assert r.status_code == 409, (path, r.text)


def test_not_found_returns_404(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="nf@example.com")
    access = _login(test_client, admin)
    ghost = uuid.uuid4()
    r = test_client.post(f"/filings/{ghost}/approve", headers=_auth_headers(access))
    assert r.status_code == 404
