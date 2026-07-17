"""End-to-end tests for /imports.

Runs the RQ job in-process via ``settings.queue_async=False`` so the test
can assert on the completed job state without needing a real worker
container. Uses a per-test ``tmp_path`` as the upload dir so parallel
runs don't collide.
"""
from __future__ import annotations

import io
import json
import uuid
from datetime import date

import pyotp
import pytest
from sqlalchemy import text

from app.config import settings
from app.db import owner_engine


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


@pytest.fixture(autouse=True)
def _sync_queue_and_tmp_upload(monkeypatch, tmp_path) -> None:
    """Force synchronous RQ execution + per-test upload directory."""
    monkeypatch.setattr(settings, "queue_async", False)
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))


@pytest.fixture
def gstin_profile(bootstrap_firm):
    """Attach a gstin_profile to the bootstrapped firm and return
    (admin_dict, gstin_profile_id)."""
    admin = bootstrap_firm(admin_email="importer@example.com")
    gid = uuid.uuid4()
    with owner_engine.begin() as conn:
        client_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:cid, :fid, 'Import Test Client')"
            ),
            {"cid": client_id, "fid": admin["firm_id"]},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code) "
                "VALUES (:gid, :fid, :cid, '29ABCDE1234F1Z5', '29')"
            ),
            {"gid": gid, "fid": admin["firm_id"], "cid": client_id},
        )
    return admin, gid


PURCHASE_CSV = (
    "invoice_number,invoice_date,counterparty_gstin,taxable_value,"
    "cgst,sgst,igst,total,hsn_sac\n"
    "INV-001,15-06-2026,29AAAAA0000A1Z5,1000,90,90,0,1180,9983\n"
    "INV-002,20-06-2026,27BBBBB0000B1Z8,2000,0,0,360,2360,9983\n"
    "bad-row,not-a-date,,1000,,,,,\n"  # rejected
)


def test_purchase_csv_upload_end_to_end(test_client, gstin_profile) -> None:
    admin, gid = gstin_profile
    access = _login(test_client, admin)

    r = test_client.post(
        "/imports/invoices",
        headers={"Authorization": f"Bearer {access}"},
        data={"gstin_profile_id": str(gid), "direction": "purchase"},
        files={
            "file": ("purchase.csv", PURCHASE_CSV.encode(), "text/csv"),
        },
    )
    assert r.status_code == 202, r.text
    job = r.json()
    job_id = job["id"]

    # Sync queue → job already finished. Fetch the row.
    r = test_client.get(
        f"/imports/{job_id}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed"
    assert body["total_rows"] == 3
    assert body["accepted_rows"] == 2
    assert body["rejected_rows"] == 1
    assert body["duplicate_rows"] == 0

    # Invoices landed.
    with owner_engine.begin() as conn:
        n = conn.execute(
            text(
                "SELECT count(*) FROM invoice WHERE gstin_profile_id = :gid"
            ),
            {"gid": str(gid)},
        ).scalar()
    assert n == 2


def test_duplicate_upload_is_deduped_by_content_hash(
    test_client, gstin_profile
) -> None:
    admin, gid = gstin_profile
    access = _login(test_client, admin)

    def _upload():
        return test_client.post(
            "/imports/invoices",
            headers={"Authorization": f"Bearer {access}"},
            data={"gstin_profile_id": str(gid), "direction": "purchase"},
            files={"file": ("p.csv", PURCHASE_CSV.encode(), "text/csv")},
        )

    r1 = _upload()
    assert r1.status_code == 202
    r2 = _upload()
    assert r2.status_code == 202

    r = test_client.get(
        f"/imports/{r2.json()['id']}",
        headers={"Authorization": f"Bearer {access}"},
    )
    body = r.json()
    assert body["accepted_rows"] == 0
    assert body["duplicate_rows"] == 2
    assert body["rejected_rows"] == 1  # 'bad-row' still rejected on second pass


def test_error_report_download(test_client, gstin_profile) -> None:
    admin, gid = gstin_profile
    access = _login(test_client, admin)
    test_client.post(
        "/imports/invoices",
        headers={"Authorization": f"Bearer {access}"},
        data={"gstin_profile_id": str(gid), "direction": "purchase"},
        files={"file": ("p.csv", PURCHASE_CSV.encode(), "text/csv")},
    )
    # Grab the just-created job
    jobs = test_client.get(
        "/imports", headers={"Authorization": f"Bearer {access}"}
    ).json()
    job_id = jobs[0]["id"]

    r = test_client.get(
        f"/imports/{job_id}/errors.csv",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    body = r.text
    assert "row_index" in body
    assert "bad-row" in body  # the offending invoice_number


def test_gstr2b_upload_end_to_end(test_client, gstin_profile) -> None:
    admin, gid = gstin_profile
    access = _login(test_client, admin)
    sample = {
        "data": {
            "rtnprd": "062026",
            "docdata": {
                "b2b": [
                    {
                        "ctin": "29AAAAA0000A1Z5",
                        "inv": [
                            {
                                "inum": "INV-100",
                                "idt": "15-06-2026",
                                "val": 1180,
                                "itcavl": "Y",
                                "items": [
                                    {"txval": 1000, "camt": 90, "samt": 90,
                                     "iamt": 0, "csamt": 0},
                                ],
                            }
                        ],
                    }
                ]
            },
        }
    }
    r = test_client.post(
        "/imports/gstr2b",
        headers={"Authorization": f"Bearer {access}"},
        data={"gstin_profile_id": str(gid), "period": "202606"},
        files={"file": ("2b.json", json.dumps(sample).encode(), "application/json")},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["kind"] == "gstr2b_json"

    r = test_client.get(
        f"/imports/{body['id']}",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 200
    completed = r.json()
    assert completed["status"] == "completed"
    assert completed["accepted_rows"] == 1
    assert completed["rejected_rows"] == 0

    with owner_engine.begin() as conn:
        n = conn.execute(
            text(
                "SELECT count(*) FROM b2b_entry WHERE gstn_pull_id IN "
                "(SELECT id FROM gstn_pull WHERE gstin_profile_id = :gid)"
            ),
            {"gid": str(gid)},
        ).scalar()
    assert n == 1


def test_cross_firm_import_job_not_visible(test_client, bootstrap_firm) -> None:
    """RLS on import_job: firm A admin cannot see firm B's jobs."""
    admin_a = bootstrap_firm(firm_name="Firm A", admin_email="a-imp@example.com")
    admin_b = bootstrap_firm(firm_name="Firm B", admin_email="b-imp@example.com")

    # Give firm B a gstin_profile and create a job through its API.
    gid_b = uuid.uuid4()
    with owner_engine.begin() as conn:
        client_id = uuid.uuid4()
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:cid, :fid, 'C')"
            ),
            {"cid": client_id, "fid": admin_b["firm_id"]},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code) "
                "VALUES (:gid, :fid, :cid, '27BBBBB0000B1Z8', '27')"
            ),
            {"gid": gid_b, "fid": admin_b["firm_id"], "cid": client_id},
        )

    access_b = _login(test_client, admin_b)
    r = test_client.post(
        "/imports/invoices",
        headers={"Authorization": f"Bearer {access_b}"},
        data={"gstin_profile_id": str(gid_b), "direction": "purchase"},
        files={"file": ("p.csv", PURCHASE_CSV.encode(), "text/csv")},
    )
    assert r.status_code == 202, r.text
    job_b_id = r.json()["id"]

    # Firm A admin tries to fetch firm B's job -> 404 (RLS filters, ORM
    # sees no row, endpoint returns 404).
    access_a = _login(test_client, admin_a)
    r = test_client.get(
        f"/imports/{job_b_id}",
        headers={"Authorization": f"Bearer {access_a}"},
    )
    assert r.status_code == 404, r.text

    # And listing from firm A doesn't include it.
    r = test_client.get(
        "/imports",
        headers={"Authorization": f"Bearer {access_a}"},
    )
    ids = [j["id"] for j in r.json()]
    assert job_b_id not in ids
