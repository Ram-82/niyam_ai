"""HTTP-level tests for the narrator API endpoints.

Covers:
* POST /narrator/preview   — happy path, flag-off 503, no-snapshot 409
* GET  /narrator/runs      — list + per-gstin filter
* GET  /narrator/runs/{id}/pdf — renders PDF bytes

Service-layer correctness (hallucination retry, audit trail, …) is in
test_narrator_service.py. These tests focus on the HTTP contract.
"""
from __future__ import annotations

import json
import uuid

import pyotp
import pytest
from sqlalchemy import text

from app.config import settings
from app.db import owner_engine
from app.engines.validation.gstin import compute_check_digit


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _narrator_mock(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "narrator_enabled", True)
    monkeypatch.setattr(settings, "narrator_mode", "mock")


def _login(client, admin: dict) -> str:
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


def _gstin(base: str) -> str:
    return base + compute_check_digit(base)


def _seed(bootstrap: dict) -> uuid.UUID:
    """Create a gstin_profile with a readiness snapshot (and its deps)."""
    firm_id = bootstrap["firm_id"]
    client_id = uuid.uuid4()
    gpid = uuid.uuid4()
    period = "202607"
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name) "
                "VALUES (:cid, :fid, 'Acme Traders')"
            ),
            {"cid": client_id, "fid": firm_id},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile (id, firm_id, client_id, gstin, state_code) "
                "VALUES (:gid, :fid, :cid, :gstin, '29')"
            ),
            {
                "gid": gpid,
                "fid": firm_id,
                "cid": client_id,
                "gstin": _gstin("29ABCDE1234F1Z"),
            },
        )
        pull_id = conn.execute(
            text(
                "INSERT INTO gstn_pull (firm_id, gstin_profile_id, return_type, "
                "period, raw_payload, source) "
                "VALUES (:fid, :gpid, 'GSTR2B', :p, CAST('{}' AS JSONB), 'json_import') "
                "RETURNING id"
            ),
            {"fid": str(firm_id), "gpid": str(gpid), "p": period},
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO reconciliation_run "
                "(firm_id, gstin_profile_id, period, rule_pack_version, gstn_pull_id, summary) "
                "VALUES (:fid, :gpid, :p, '1.0.0', :pid, CAST(:s AS JSONB))"
            ),
            {
                "fid": str(firm_id),
                "gpid": str(gpid),
                "p": period,
                "pid": str(pull_id),
                "s": json.dumps(
                    {
                        "matched": {"count": 2, "paise": 1_00_00_000},
                        "probable": {"count": 1, "paise": 50_00_000},
                        "supplier_default": {
                            "count": 3,
                            "paise": 20_00_000,
                            "top_suppliers": [],
                        },
                        "missing_entry": {"count": 2, "paise": 60_00_000},
                    }
                ),
            },
        )
        conn.execute(
            text(
                "INSERT INTO readiness_snapshot "
                "(firm_id, gstin_profile_id, return_type, period, "
                "score, blockers, arithmetic, rule_pack_version) "
                "VALUES (:fid, :gpid, 'GSTR1', :p, "
                "72, CAST(:b AS JSONB), CAST(:a AS JSONB), '1.0.0')"
            ),
            {
                "fid": str(firm_id),
                "gpid": str(gpid),
                "p": period,
                "b": json.dumps(
                    [
                        {
                            "kind": "supplier_default",
                            "owner": "ca",
                            "description": "ITC risk from 3 suppliers",
                            "paise_impact": 20_00_000,
                        }
                    ]
                ),
                "a": json.dumps(
                    {"tax_paid_paise": 15_00_000, "tax_due_paise": 20_00_000}
                ),
            },
        )
    return gpid


# ---------------------------------------------------------------------------
# POST /narrator/preview
# ---------------------------------------------------------------------------


def test_preview_happy_path(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="nar-preview@example.com")
    gpid = _seed(admin)
    token = _login(test_client, admin)

    r = test_client.post(
        "/narrator/preview",
        json={
            "gstin_profile_id": str(gpid),
            "period": "202607",
            "return_type": "GSTR1",
            "language": "en",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert uuid.UUID(data["narration_run_id"])
    assert data["provider"] == "mock"
    assert data["language"] == "en"
    for block in ("page1_health", "page1_tax_position", "page2_attention", "page2_ask_your_ca"):
        assert isinstance(data[block], str)
        assert len(data[block]) > 20


def test_preview_narrator_disabled_returns_503(
    test_client, bootstrap_firm, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "narrator_enabled", False)
    admin = bootstrap_firm(admin_email="nar-disabled@example.com")
    gpid = _seed(admin)
    token = _login(test_client, admin)

    r = test_client.post(
        "/narrator/preview",
        json={
            "gstin_profile_id": str(gpid),
            "period": "202607",
            "return_type": "GSTR1",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 503
    assert r.json()["detail"] == "narrator_disabled"


def test_preview_no_snapshot_returns_409(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="nar-no-snap@example.com")
    token = _login(test_client, admin)

    # Use a random UUID that has no seeded data.
    r = test_client.post(
        "/narrator/preview",
        json={
            "gstin_profile_id": str(uuid.uuid4()),
            "period": "202607",
            "return_type": "GSTR1",
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "no_readiness_snapshot"


def test_preview_requires_auth(test_client) -> None:
    r = test_client.post(
        "/narrator/preview",
        json={"gstin_profile_id": str(uuid.uuid4()), "period": "202607", "return_type": "GSTR1"},
    )
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# GET /narrator/runs
# ---------------------------------------------------------------------------


def test_list_runs_returns_generated_run(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="nar-list@example.com")
    gpid = _seed(admin)
    token = _login(test_client, admin)

    # Generate one run first.
    test_client.post(
        "/narrator/preview",
        json={"gstin_profile_id": str(gpid), "period": "202607", "return_type": "GSTR1"},
        headers={"Authorization": f"Bearer {token}"},
    )

    r = test_client.get("/narrator/runs", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 1
    assert any(row["gstin_profile_id"] == str(gpid) for row in rows)


def test_list_runs_filtered_by_gstin(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="nar-filter@example.com")
    gpid = _seed(admin)
    token = _login(test_client, admin)

    test_client.post(
        "/narrator/preview",
        json={"gstin_profile_id": str(gpid), "period": "202607", "return_type": "GSTR1"},
        headers={"Authorization": f"Bearer {token}"},
    )

    other_gpid = uuid.uuid4()
    r = test_client.get(
        f"/narrator/runs?gstin_profile_id={other_gpid}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == []


def test_list_runs_firm_isolation(test_client, bootstrap_firm) -> None:
    """Runs generated by firm A must not be visible to firm B."""
    firm_a = bootstrap_firm(admin_email="nar-iso-a@example.com")
    firm_b = bootstrap_firm(admin_email="nar-iso-b@example.com")
    gpid = _seed(firm_a)
    token_a = _login(test_client, firm_a)
    token_b = _login(test_client, firm_b)

    test_client.post(
        "/narrator/preview",
        json={"gstin_profile_id": str(gpid), "period": "202607", "return_type": "GSTR1"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    r = test_client.get("/narrator/runs", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 200
    # Firm B should see none of firm A's runs.
    assert all(row["gstin_profile_id"] != str(gpid) for row in r.json())


# ---------------------------------------------------------------------------
# GET /narrator/runs/{id}/pdf
# ---------------------------------------------------------------------------


def test_get_pdf_returns_pdf_bytes(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="nar-pdf@example.com")
    gpid = _seed(admin)
    token = _login(test_client, admin)

    preview = test_client.post(
        "/narrator/preview",
        json={"gstin_profile_id": str(gpid), "period": "202607", "return_type": "GSTR1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert preview.status_code == 200
    run_id = preview.json()["narration_run_id"]

    r = test_client.get(
        f"/narrator/runs/{run_id}/pdf",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_get_pdf_unknown_id_returns_404(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(admin_email="nar-pdf-404@example.com")
    token = _login(test_client, admin)

    r = test_client.get(
        f"/narrator/runs/{uuid.uuid4()}/pdf",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "narration_run_not_found"


def test_get_pdf_firm_isolation(test_client, bootstrap_firm) -> None:
    """Firm B cannot download firm A's narration PDF."""
    firm_a = bootstrap_firm(admin_email="nar-pdf-iso-a@example.com")
    firm_b = bootstrap_firm(admin_email="nar-pdf-iso-b@example.com")
    gpid = _seed(firm_a)
    token_a = _login(test_client, firm_a)
    token_b = _login(test_client, firm_b)

    preview = test_client.post(
        "/narrator/preview",
        json={"gstin_profile_id": str(gpid), "period": "202607", "return_type": "GSTR1"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    run_id = preview.json()["narration_run_id"]

    r = test_client.get(
        f"/narrator/runs/{run_id}/pdf",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert r.status_code == 404
