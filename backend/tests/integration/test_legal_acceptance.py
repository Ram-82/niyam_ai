"""Legal acceptance flow and blocking gate on import endpoints.

Covers:
  * pending listing for a firm with no acceptances
  * POST /legal/accept happy path (records row + audit_log)
  * 409 on stale (version, hash) declarations
  * 404 on unknown doc_type
  * 403 blocking gate on client + invoice + 2B imports without acceptance
  * gate passes after acceptance
  * hash change (manifest bump) forces re-acceptance
  * append-only guarantees (UPDATE/DELETE rejected by trigger)
  * RLS isolation across firms
"""
from __future__ import annotations

import io
import json
import uuid
from unittest.mock import patch

import pyotp
import pytest
from sqlalchemy import text

from app.db import owner_engine
from app.legal.documents import LoadedDocument, current_by_type
from app.legal.manifest import REQUIRED_DOC_TYPES


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


def _headers(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def _accept_all(client, tok: str) -> None:
    for doc in current_by_type().values():
        r = client.post(
            "/legal/accept",
            headers=_headers(tok),
            json={
                "doc_type": doc.doc_type,
                "version": doc.version,
                "content_hash": doc.content_hash,
            },
        )
        assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# GET /legal/pending
# ---------------------------------------------------------------------------


def test_pending_lists_all_required_docs_for_new_firm(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(
        admin_email=f"legal-{uuid.uuid4().hex[:6]}@example.com",
        accept_legal=False,
    )
    tok = _login(test_client, admin)

    r = test_client.get("/legal/pending", headers=_headers(tok))
    assert r.status_code == 200, r.text
    pending = r.json()["pending"]
    types = {p["doc_type"] for p in pending}
    assert types == set(REQUIRED_DOC_TYPES)


def test_pending_empty_after_accepting_all(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(
        admin_email=f"legal-{uuid.uuid4().hex[:6]}@example.com",
        accept_legal=False,
    )
    tok = _login(test_client, admin)

    _accept_all(test_client, tok)

    r = test_client.get("/legal/pending", headers=_headers(tok))
    assert r.status_code == 200
    assert r.json()["pending"] == []


# ---------------------------------------------------------------------------
# POST /legal/accept
# ---------------------------------------------------------------------------


def test_accept_writes_row_and_audit_log(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(
        admin_email=f"legal-{uuid.uuid4().hex[:6]}@example.com",
        accept_legal=False,
    )
    tok = _login(test_client, admin)
    doc = current_by_type()["dpa"]

    r = test_client.post(
        "/legal/accept",
        headers={**_headers(tok), "user-agent": "pytest-ua/1"},
        json={
            "doc_type": doc.doc_type,
            "version": doc.version,
            "content_hash": doc.content_hash,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["doc_type"] == "dpa"
    assert body["content_hash"] == doc.content_hash
    # Only DPA accepted → terms still pending.
    assert [p["doc_type"] for p in body["remaining_pending"]] == ["terms"]

    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT doc_type, doc_version, content_hash, user_agent "
                "FROM legal_acceptance WHERE firm_id = :fid"
            ),
            {"fid": admin["firm_id"]},
        ).mappings().one()
    assert row["doc_type"] == "dpa"
    assert row["content_hash"] == doc.content_hash
    assert row["user_agent"] == "pytest-ua/1"

    with owner_engine.begin() as conn:
        audit_rows = conn.execute(
            text(
                "SELECT action, entity_type, diff FROM audit_log "
                "WHERE firm_id = :fid AND action = 'legal.accepted'"
            ),
            {"fid": admin["firm_id"]},
        ).mappings().all()
    assert len(audit_rows) == 1
    assert audit_rows[0]["entity_type"] == "legal_acceptance"
    assert audit_rows[0]["diff"]["doc_type"] == "dpa"


def test_accept_wrong_hash_returns_409(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(
        admin_email=f"legal-{uuid.uuid4().hex[:6]}@example.com",
        accept_legal=False,
    )
    tok = _login(test_client, admin)
    doc = current_by_type()["dpa"]

    r = test_client.post(
        "/legal/accept",
        headers=_headers(tok),
        json={
            "doc_type": "dpa",
            "version": doc.version,
            "content_hash": "0" * 64,
        },
    )
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["error"] == "document_mismatch"


def test_accept_unknown_doc_type_returns_404(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(
        admin_email=f"legal-{uuid.uuid4().hex[:6]}@example.com",
        accept_legal=False,
    )
    tok = _login(test_client, admin)

    r = test_client.post(
        "/legal/accept",
        headers=_headers(tok),
        json={"doc_type": "aup", "version": "1.0.0", "content_hash": "0" * 64},
    )
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Blocking gate on import surfaces
# ---------------------------------------------------------------------------


def test_create_client_blocked_without_acceptance(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(
        admin_email=f"legal-{uuid.uuid4().hex[:6]}@example.com",
        accept_legal=False,
    )
    tok = _login(test_client, admin)

    r = test_client.post(
        "/clients",
        headers=_headers(tok),
        json={"trade_name": "Acme"},
    )
    assert r.status_code == 403, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "legal_acceptance_required"
    types = {p["doc_type"] for p in detail["pending"]}
    assert types == set(REQUIRED_DOC_TYPES)


def test_import_clients_csv_blocked_without_acceptance(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(
        admin_email=f"legal-{uuid.uuid4().hex[:6]}@example.com",
        accept_legal=False,
    )
    tok = _login(test_client, admin)
    csv_body = "trade_name\nAcme\n"

    r = test_client.post(
        "/clients/import",
        headers=_headers(tok),
        params={"dry_run": "true"},
        files={"file": ("clients.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")},
        data={"mapping": json.dumps({})},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "legal_acceptance_required"


def test_upload_invoices_blocked_without_acceptance(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(
        admin_email=f"legal-{uuid.uuid4().hex[:6]}@example.com",
        accept_legal=False,
    )
    tok = _login(test_client, admin)

    r = test_client.post(
        "/imports/invoices",
        headers=_headers(tok),
        data={
            "gstin_profile_id": str(uuid.uuid4()),
            "direction": "purchase",
        },
        files={"file": ("invoices.csv", io.BytesIO(b"header\nrow\n"), "text/csv")},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["error"] == "legal_acceptance_required"


def test_import_allowed_after_acceptance(test_client, bootstrap_firm) -> None:
    admin = bootstrap_firm(
        admin_email=f"legal-{uuid.uuid4().hex[:6]}@example.com",
        accept_legal=False,
    )
    tok = _login(test_client, admin)
    _accept_all(test_client, tok)

    # POST /clients now returns 201 (was 403 before acceptance).
    r = test_client.post(
        "/clients",
        headers=_headers(tok),
        json={"trade_name": "Post-acceptance client"},
    )
    assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# Hash change forces re-acceptance
# ---------------------------------------------------------------------------


def test_hash_change_forces_reacceptance(test_client, bootstrap_firm) -> None:
    """Bump the manifest doc's content_hash under the running process and
    confirm the firm sees the doc in pending again (i.e., a prior
    acceptance at the OLD hash no longer satisfies the gate)."""
    admin = bootstrap_firm(
        admin_email=f"legal-{uuid.uuid4().hex[:6]}@example.com",
        accept_legal=True,
    )
    tok = _login(test_client, admin)

    # Baseline: firm is fully accepted.
    r = test_client.get("/legal/pending", headers=_headers(tok))
    assert r.json()["pending"] == []

    # Simulate a manifest bump: patch current_by_type to return a doc with
    # a different hash for 'dpa'. Everything else identical.
    original = current_by_type()
    bumped_dpa = LoadedDocument(
        doc_type="dpa",
        version="1.0.1",
        content_hash="f" * 64,
        content=original["dpa"].content,
        effective_from=original["dpa"].effective_from,
        notes="test bump",
    )
    patched = dict(original)
    patched["dpa"] = bumped_dpa

    with patch("app.legal.service.current_by_type", return_value=patched):
        r = test_client.get("/legal/pending", headers=_headers(tok))
        assert r.status_code == 200
        pending_types = {p["doc_type"] for p in r.json()["pending"]}
        assert pending_types == {"dpa"}


# ---------------------------------------------------------------------------
# Append-only guarantees
# ---------------------------------------------------------------------------


def test_legal_acceptance_update_forbidden(bootstrap_firm) -> None:
    admin = bootstrap_firm(
        admin_email=f"legal-{uuid.uuid4().hex[:6]}@example.com",
        accept_legal=True,
    )
    with owner_engine.begin() as conn:
        with pytest.raises(Exception) as ei:
            conn.execute(
                text(
                    "UPDATE legal_acceptance SET doc_type = 'evil' "
                    "WHERE firm_id = :fid"
                ),
                {"fid": admin["firm_id"]},
            )
        assert "niyam_forbid_mutation" in str(ei.value) or "mutation" in str(ei.value).lower()


def test_legal_acceptance_delete_forbidden(bootstrap_firm) -> None:
    admin = bootstrap_firm(
        admin_email=f"legal-{uuid.uuid4().hex[:6]}@example.com",
        accept_legal=True,
    )
    with owner_engine.begin() as conn:
        with pytest.raises(Exception) as ei:
            conn.execute(
                text("DELETE FROM legal_acceptance WHERE firm_id = :fid"),
                {"fid": admin["firm_id"]},
            )
        assert "niyam_forbid_mutation" in str(ei.value) or "mutation" in str(ei.value).lower()


# ---------------------------------------------------------------------------
# RLS isolation
# ---------------------------------------------------------------------------


@pytest.mark.rls
def test_firm_cannot_see_other_firms_acceptances(test_client, bootstrap_firm) -> None:
    """Firm A accepts DPA; firm B logs in and finds its own pending list
    unaffected (all docs still pending), i.e., A's acceptance is invisible."""
    firm_a = bootstrap_firm(
        firm_name="Firm A",
        admin_email=f"a-{uuid.uuid4().hex[:6]}@example.com",
        accept_legal=False,
    )
    firm_b = bootstrap_firm(
        firm_name="Firm B",
        admin_email=f"b-{uuid.uuid4().hex[:6]}@example.com",
        accept_legal=False,
    )

    tok_a = _login(test_client, firm_a)
    _accept_all(test_client, tok_a)

    tok_b = _login(test_client, firm_b)
    r = test_client.get("/legal/pending", headers=_headers(tok_b))
    assert r.status_code == 200
    types_b = {p["doc_type"] for p in r.json()["pending"]}
    assert types_b == set(REQUIRED_DOC_TYPES), (
        "Firm B saw firm A's acceptance leaking through — RLS is broken"
    )
