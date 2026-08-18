"""HTTP-level tests for /ocr/* endpoints (P2.1 Step 2 surface).

Covers:

POST /ocr/invoice
    * Feature flag off → 503.
    * Unauthenticated → 401.
    * Unsupported extension → 415.
    * Empty upload → 400.
    * Oversized upload → 413.
    * Unknown / cross-firm gstin_profile_id → 404 (no row inserted, no audit).
    * Happy path with pinned fixture → 201 + persisted row + audit_log row.
    * Happy path with unknown bytes → 201 + low-confidence synthetic row.

GET /ocr/extractions
    * Lists caller's rows only (RLS isolation across firms).
    * Filters on gstin_profile_id.
    * Filters on status.
    * Respects limit.

GET /ocr/extractions/{id}
    * Full extraction detail (per-field payload).
    * Cross-firm id → 404.
    * Unknown id → 404.

Unit-level adapter correctness lives in
``tests/unit/test_ocr_mock_adapter.py``. Service-layer persistence is
covered by ``tests/integration/test_ocr_service.py``.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pyotp
import pytest
from sqlalchemy import text

from app.config import settings
from app.db import owner_engine
from app.engines.validation.gstin import compute_check_digit


FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "ocr"
    / "fixtures"
    / "sample_invoice_1.txt"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _enable_ocr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ocr_enabled", True)
    monkeypatch.setattr(settings, "ocr_mode", "mock")


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


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _gstin(base: str) -> str:
    return base + compute_check_digit(base)


def _seed_gstin(firm_id: uuid.UUID, base: str = "29ABCDE1234F1Z") -> uuid.UUID:
    """Create a client + gstin_profile under ``firm_id``. Returns the profile id."""
    client_id = uuid.uuid4()
    gpid = uuid.uuid4()
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
                "VALUES (:gid, :fid, :cid, :gstin, :state)"
            ),
            {
                "gid": gpid,
                "fid": firm_id,
                "cid": client_id,
                "gstin": _gstin(base),
                "state": base[:2],
            },
        )
    return gpid


# ---------------------------------------------------------------------------
# POST /ocr/invoice — feature flag / auth / validation
# ---------------------------------------------------------------------------


class TestFeatureFlag:
    def test_flag_off_returns_503(
        self,
        test_client,
        bootstrap_firm,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "ocr_enabled", False)
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])
        r = test_client.post(
            "/ocr/invoice",
            headers=_auth_headers(token),
            data={"direction": "purchase", "gstin_profile_id": str(gpid)},
            files={"file": ("a.pdf", b"anything", "application/pdf")},
        )
        assert r.status_code == 503
        assert r.json()["detail"] == "ocr_disabled"


class TestAuth:
    def test_missing_bearer_token_returns_401(self, test_client) -> None:
        r = test_client.post(
            "/ocr/invoice",
            data={
                "direction": "purchase",
                "gstin_profile_id": str(uuid.uuid4()),
            },
            files={"file": ("a.pdf", b"anything", "application/pdf")},
        )
        assert r.status_code == 401


class TestUploadValidation:
    def test_unsupported_extension_returns_415(
        self, test_client, bootstrap_firm
    ) -> None:
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])
        r = test_client.post(
            "/ocr/invoice",
            headers=_auth_headers(token),
            data={"direction": "purchase", "gstin_profile_id": str(gpid)},
            files={"file": ("a.docx", b"anything", "application/octet-stream")},
        )
        assert r.status_code == 415
        assert ".docx" in r.json()["detail"]

    def test_empty_upload_returns_400(
        self, test_client, bootstrap_firm
    ) -> None:
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])
        r = test_client.post(
            "/ocr/invoice",
            headers=_auth_headers(token),
            data={"direction": "purchase", "gstin_profile_id": str(gpid)},
            files={"file": ("a.pdf", b"", "application/pdf")},
        )
        assert r.status_code == 400
        assert r.json()["detail"] == "empty upload"

    def test_oversized_upload_returns_413(
        self,
        test_client,
        bootstrap_firm,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "ocr_max_upload_bytes", 100)
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])
        r = test_client.post(
            "/ocr/invoice",
            headers=_auth_headers(token),
            data={"direction": "purchase", "gstin_profile_id": str(gpid)},
            files={"file": ("a.pdf", b"x" * 200, "application/pdf")},
        )
        assert r.status_code == 413


class TestCrossFirmGstinProfile:
    def test_unknown_gstin_profile_returns_404_and_writes_nothing(
        self, test_client, bootstrap_firm
    ) -> None:
        """A probe with a random / cross-firm gstin_profile_id must
        return 404 AND leave no ocr_extraction or audit_log row —
        otherwise a caller could enumerate which UUIDs exist elsewhere
        by watching for side effects."""
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        other_firm_gpid = uuid.uuid4()  # a UUID that does not exist anywhere

        r = test_client.post(
            "/ocr/invoice",
            headers=_auth_headers(token),
            data={
                "direction": "purchase",
                "gstin_profile_id": str(other_firm_gpid),
            },
            files={"file": ("a.pdf", b"anything", "application/pdf")},
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "gstin_profile not found"

        # No side effects.
        with owner_engine.begin() as conn:
            ocr_count = conn.execute(
                text(
                    "SELECT count(*) FROM ocr_extraction WHERE firm_id = :fid"
                ),
                {"fid": str(admin["firm_id"])},
            ).scalar()
            audit_count = conn.execute(
                text(
                    "SELECT count(*) FROM audit_log "
                    "WHERE firm_id = :fid AND action = 'ocr.extracted'"
                ),
                {"fid": str(admin["firm_id"])},
            ).scalar()
        assert ocr_count == 0
        assert audit_count == 0


# ---------------------------------------------------------------------------
# POST /ocr/invoice — happy path (persist + audit)
# ---------------------------------------------------------------------------


class TestFixtureExtractionHappyPath:
    def test_fixture_persists_and_audits(
        self, test_client, bootstrap_firm
    ) -> None:
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])
        content = FIXTURE_PATH.read_bytes()

        r = test_client.post(
            "/ocr/invoice",
            headers=_auth_headers(token),
            data={"direction": "purchase", "gstin_profile_id": str(gpid)},
            files={
                "file": ("sample_invoice_1.txt", content, "text/plain"),
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()

        # Persisted identity fields.
        ocr_id = uuid.UUID(body["id"])
        assert uuid.UUID(body["firm_id"]) == admin["firm_id"]
        assert uuid.UUID(body["gstin_profile_id"]) == gpid
        assert body["direction"] == "purchase"
        assert body["status"] == "draft"
        assert body["created_at"] is not None

        # Adapter + pinned fixture fields.
        assert body["adapter"] == "mock"
        assert body["supplier_gstin"]["value"] == "29ABCDE1234F1Z5"
        assert body["overall_confidence"] == 1.0
        assert body["warnings"] == []

        # DB row present.
        with owner_engine.begin() as conn:
            row = conn.execute(
                text(
                    "SELECT status, adapter, overall_confidence "
                    "FROM ocr_extraction WHERE id = :i"
                ),
                {"i": str(ocr_id)},
            ).mappings().first()
            assert row is not None
            assert row["status"] == "draft"
            assert row["adapter"] == "mock"
            assert float(row["overall_confidence"]) == 1.0

            # Audit row present.
            audit_rows = conn.execute(
                text(
                    "SELECT diff FROM audit_log "
                    "WHERE firm_id = :fid AND action = 'ocr.extracted' "
                    "AND entity_id = :i"
                ),
                {"fid": str(admin["firm_id"]), "i": str(ocr_id)},
            ).fetchall()
            assert len(audit_rows) == 1

    def test_synthetic_low_confidence_extraction_persists(
        self, test_client, bootstrap_firm
    ) -> None:
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])

        r = test_client.post(
            "/ocr/invoice",
            headers=_auth_headers(token),
            data={"direction": "purchase", "gstin_profile_id": str(gpid)},
            files={"file": ("mystery.pdf", b"not a known fixture", "application/pdf")},
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["overall_confidence"] < settings.ocr_low_confidence_threshold
        assert any("no fixture matched" in w for w in body["warnings"])
        assert body["supplier_gstin"]["value"] is None


# ---------------------------------------------------------------------------
# GET /ocr/extractions — list + filters + RLS
# ---------------------------------------------------------------------------


def _post_extraction(
    test_client, token: str, gpid: uuid.UUID, filename: str, content: bytes
) -> uuid.UUID:
    r = test_client.post(
        "/ocr/invoice",
        headers=_auth_headers(token),
        data={"direction": "purchase", "gstin_profile_id": str(gpid)},
        files={"file": (filename, content, "application/pdf")},
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


class TestListExtractions:
    def test_list_returns_only_own_firm_rows(
        self, test_client, bootstrap_firm
    ) -> None:
        admin_a = bootstrap_firm(admin_email=f"a-{uuid.uuid4().hex[:6]}@example.com")
        admin_b = bootstrap_firm(admin_email=f"b-{uuid.uuid4().hex[:6]}@example.com")
        token_a = _login(test_client, admin_a)
        token_b = _login(test_client, admin_b)
        gpid_a = _seed_gstin(admin_a["firm_id"], base="29AAAAA1234F1Z")
        gpid_b = _seed_gstin(admin_b["firm_id"], base="27BBBBB5678F1Z")

        id_a = _post_extraction(test_client, token_a, gpid_a, "a.pdf", b"firm-a bytes")
        id_b = _post_extraction(test_client, token_b, gpid_b, "b.pdf", b"firm-b bytes")

        r = test_client.get("/ocr/extractions", headers=_auth_headers(token_a))
        assert r.status_code == 200
        rows = r.json()
        ids = {uuid.UUID(row["id"]) for row in rows}
        assert id_a in ids
        assert id_b not in ids

    def test_list_filters_by_gstin_profile_id(
        self, test_client, bootstrap_firm
    ) -> None:
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid_1 = _seed_gstin(admin["firm_id"], base="29CCCCC1234F1Z")
        gpid_2 = _seed_gstin(admin["firm_id"], base="29DDDDD5678F1Z")

        id_1 = _post_extraction(test_client, token, gpid_1, "1.pdf", b"one")
        id_2 = _post_extraction(test_client, token, gpid_2, "2.pdf", b"two")

        r = test_client.get(
            f"/ocr/extractions?gstin_profile_id={gpid_1}",
            headers=_auth_headers(token),
        )
        assert r.status_code == 200
        ids = {uuid.UUID(row["id"]) for row in r.json()}
        assert ids == {id_1}
        assert id_2 not in ids

    def test_list_respects_limit(
        self, test_client, bootstrap_firm
    ) -> None:
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])
        for i in range(3):
            _post_extraction(test_client, token, gpid, f"{i}.pdf", f"bytes-{i}".encode())

        r = test_client.get(
            "/ocr/extractions?limit=2", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        assert len(r.json()) == 2


# ---------------------------------------------------------------------------
# GET /ocr/extractions/{id} — detail + RLS isolation
# ---------------------------------------------------------------------------


class TestGetExtraction:
    def test_detail_returns_full_payload(
        self, test_client, bootstrap_firm
    ) -> None:
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])
        content = FIXTURE_PATH.read_bytes()

        ocr_id = _post_extraction(
            test_client, token, gpid, "sample_invoice_1.txt", content
        )

        r = test_client.get(
            f"/ocr/extractions/{ocr_id}", headers=_auth_headers(token)
        )
        assert r.status_code == 200
        body = r.json()
        assert uuid.UUID(body["id"]) == ocr_id
        # Per-field payload survives the JSONB round trip.
        assert body["supplier_gstin"]["value"] == "29ABCDE1234F1Z5"
        assert body["total_paise"]["value"] == "1180000"
        assert body["overall_confidence"] == 1.0

    def test_detail_for_other_firm_returns_404(
        self, test_client, bootstrap_firm
    ) -> None:
        """RLS scopes the SELECT — a valid extraction id from firm B
        is invisible to firm A and must 404 (never leak existence)."""
        admin_a = bootstrap_firm(admin_email=f"a-{uuid.uuid4().hex[:6]}@example.com")
        admin_b = bootstrap_firm(admin_email=f"b-{uuid.uuid4().hex[:6]}@example.com")
        token_a = _login(test_client, admin_a)
        token_b = _login(test_client, admin_b)
        gpid_b = _seed_gstin(admin_b["firm_id"], base="27EEEEE1234F1Z")

        id_b = _post_extraction(test_client, token_b, gpid_b, "b.pdf", b"firm-b bytes")

        r = test_client.get(
            f"/ocr/extractions/{id_b}", headers=_auth_headers(token_a)
        )
        assert r.status_code == 404
        assert r.json()["detail"] == "extraction not found"

    def test_detail_for_unknown_id_returns_404(
        self, test_client, bootstrap_firm
    ) -> None:
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        r = test_client.get(
            f"/ocr/extractions/{uuid.uuid4()}", headers=_auth_headers(token)
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# POST /ocr/invoice — real pdfminer adapter (Step 3a)
# ---------------------------------------------------------------------------


_PDFMINER_INVOICE_HTML = """
<!DOCTYPE html>
<html>
<body style="font-family: sans-serif;">
  <h1>TAX INVOICE</h1>
  <p>Supplier GSTIN: 29ABCDE1234F1ZW</p>
  <p>Invoice No: INV-2026-0042</p>
  <p>Invoice Date: 2026-07-20</p>
  <p>HSN: 998311</p>
  <p>Taxable Value: 5,000.00</p>
  <p>CGST: 450.00</p>
  <p>SGST: 450.00</p>
  <p>IGST: 0.00</p>
  <p>Grand Total: 5,900.00</p>
</body>
</html>
"""


@pytest.fixture(scope="module")
def pdfminer_invoice_pdf() -> bytes:
    """Session-scoped fixture: generate a real PDF for the pdfminer
    adapter integration test."""
    from weasyprint import HTML
    return HTML(string=_PDFMINER_INVOICE_HTML).write_pdf()


class TestPdfMinerModeEndToEnd:
    def test_post_with_pdfminer_mode_extracts_and_persists(
        self,
        test_client,
        bootstrap_firm,
        pdfminer_invoice_pdf: bytes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "ocr_mode", "pdfminer")
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])

        r = test_client.post(
            "/ocr/invoice",
            headers=_auth_headers(token),
            data={"direction": "purchase", "gstin_profile_id": str(gpid)},
            files={
                "file": ("invoice.pdf", pdfminer_invoice_pdf, "application/pdf"),
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()

        # Adapter attribution — end-to-end proof we ran pdfminer, not mock.
        assert body["adapter"] == "pdfminer"
        assert body["status"] == "draft"

        # Pdfminer + extractors together should pull labeled fields.
        assert body["supplier_gstin"]["value"] == "29ABCDE1234F1ZW"
        assert body["supplier_gstin"]["confidence"] == 1.0
        assert body["invoice_number"]["value"] == "INV-2026-0042"
        assert body["invoice_date"]["value"] == "2026-07-20"
        assert body["taxable_value_paise"]["value"] == "500000"
        assert body["total_paise"]["value"] == "590000"
        assert body["hsn_sac"]["value"] == "998311"

        # Arithmetic checks out → no warning.
        assert body["warnings"] == []

        # Persisted row is queryable via the detail endpoint.
        ocr_id = body["id"]
        r2 = test_client.get(
            f"/ocr/extractions/{ocr_id}", headers=_auth_headers(token)
        )
        assert r2.status_code == 200
        assert r2.json()["adapter"] == "pdfminer"


# ---------------------------------------------------------------------------
# POST /ocr/extractions/{id}/accept  and  /reject  (Step 4)
# ---------------------------------------------------------------------------


def _post_pdfminer_extraction(
    test_client, token: str, gpid: uuid.UUID, pdf_bytes: bytes
) -> uuid.UUID:
    """Helper: post a real pdfminer extraction (all required fields present)."""
    r = test_client.post(
        "/ocr/invoice",
        headers=_auth_headers(token),
        data={"direction": "purchase", "gstin_profile_id": str(gpid)},
        files={"file": ("invoice.pdf", pdf_bytes, "application/pdf")},
    )
    assert r.status_code == 201, r.text
    return uuid.UUID(r.json()["id"])


class TestAcceptExtraction:
    def test_accept_creates_invoice_and_locks_row(
        self,
        test_client,
        bootstrap_firm,
        pdfminer_invoice_pdf: bytes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "ocr_mode", "pdfminer")
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])

        ocr_id = _post_pdfminer_extraction(
            test_client, token, gpid, pdfminer_invoice_pdf
        )

        r = test_client.post(
            f"/ocr/extractions/{ocr_id}/accept",
            headers=_auth_headers(token),
            json={},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "accepted"
        invoice_id = uuid.UUID(body["invoice_id"])

        # Persisted Invoice row is present + sourced from ocr.
        with owner_engine.begin() as conn:
            inv = conn.execute(
                text(
                    "SELECT source, invoice_number, taxable_value_paise, "
                    "total_paise, counterparty_gstin "
                    "FROM invoice WHERE id = :i"
                ),
                {"i": str(invoice_id)},
            ).mappings().first()
            assert inv is not None
            assert inv["source"] == "ocr"
            assert inv["invoice_number"] == "INV-2026-0042"
            assert inv["taxable_value_paise"] == 500_000
            assert inv["total_paise"] == 590_000
            assert inv["counterparty_gstin"] == "29ABCDE1234F1ZW"

            # ocr_extraction row is locked.
            ocr = conn.execute(
                text(
                    "SELECT status, invoice_id, decided_by, decided_at "
                    "FROM ocr_extraction WHERE id = :i"
                ),
                {"i": str(ocr_id)},
            ).mappings().first()
            assert ocr["status"] == "accepted"
            assert uuid.UUID(str(ocr["invoice_id"])) == invoice_id
            assert ocr["decided_at"] is not None
            assert uuid.UUID(str(ocr["decided_by"])) == admin["user_id"]

            # Audit row.
            audits = conn.execute(
                text(
                    "SELECT diff FROM audit_log "
                    "WHERE firm_id = :fid AND action = 'ocr.accepted' "
                    "AND entity_id = :i"
                ),
                {"fid": str(admin["firm_id"]), "i": str(ocr_id)},
            ).fetchall()
            assert len(audits) == 1

    def test_accept_with_edited_fields_uses_ca_values(
        self,
        test_client,
        bootstrap_firm,
        pdfminer_invoice_pdf: bytes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "ocr_mode", "pdfminer")
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])

        ocr_id = _post_pdfminer_extraction(
            test_client, token, gpid, pdfminer_invoice_pdf
        )

        r = test_client.post(
            f"/ocr/extractions/{ocr_id}/accept",
            headers=_auth_headers(token),
            json={
                "edited_fields": {
                    "invoice_number": "INV-CA-EDITED-1",
                    "total_paise": "600000",  # CA overrides
                }
            },
        )
        assert r.status_code == 200, r.text
        invoice_id = uuid.UUID(r.json()["invoice_id"])

        with owner_engine.begin() as conn:
            inv = conn.execute(
                text(
                    "SELECT invoice_number, total_paise "
                    "FROM invoice WHERE id = :i"
                ),
                {"i": str(invoice_id)},
            ).mappings().first()
            assert inv["invoice_number"] == "INV-CA-EDITED-1"
            assert inv["total_paise"] == 600_000  # CA's edit, not the extracted 590_000

            # edited_extraction persisted alongside raw.
            ocr = conn.execute(
                text(
                    "SELECT edited_extraction, raw_extraction "
                    "FROM ocr_extraction WHERE id = :i"
                ),
                {"i": str(ocr_id)},
            ).mappings().first()
            assert ocr["edited_extraction"] == {
                "invoice_number": "INV-CA-EDITED-1",
                "total_paise": "600000",
            }
            # Raw survived — trigger from migration 0019 forbids mutation.
            assert (ocr["raw_extraction"] or {}).get(
                "invoice_number", {}
            ).get("value") == "INV-2026-0042"

    def test_double_accept_returns_409(
        self,
        test_client,
        bootstrap_firm,
        pdfminer_invoice_pdf: bytes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "ocr_mode", "pdfminer")
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])

        ocr_id = _post_pdfminer_extraction(
            test_client, token, gpid, pdfminer_invoice_pdf
        )

        r1 = test_client.post(
            f"/ocr/extractions/{ocr_id}/accept",
            headers=_auth_headers(token),
            json={},
        )
        assert r1.status_code == 200

        r2 = test_client.post(
            f"/ocr/extractions/{ocr_id}/accept",
            headers=_auth_headers(token),
            json={},
        )
        assert r2.status_code == 409
        assert r2.json()["detail"] == "extraction already decided"

    def test_accept_cross_firm_returns_404(
        self,
        test_client,
        bootstrap_firm,
        pdfminer_invoice_pdf: bytes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "ocr_mode", "pdfminer")
        admin_a = bootstrap_firm(admin_email=f"a-{uuid.uuid4().hex[:6]}@example.com")
        admin_b = bootstrap_firm(admin_email=f"b-{uuid.uuid4().hex[:6]}@example.com")
        token_a = _login(test_client, admin_a)
        token_b = _login(test_client, admin_b)
        gpid_b = _seed_gstin(admin_b["firm_id"], base="27FFFFF1234F1Z")

        ocr_id_b = _post_pdfminer_extraction(
            test_client, token_b, gpid_b, pdfminer_invoice_pdf
        )

        r = test_client.post(
            f"/ocr/extractions/{ocr_id_b}/accept",
            headers=_auth_headers(token_a),
            json={},
        )
        assert r.status_code == 404

    def test_accept_with_missing_required_field_returns_422(
        self,
        test_client,
        bootstrap_firm,
    ) -> None:
        """A mock-mode synthetic extraction has ``supplier_gstin=null``;
        accepting it without an edit for that field must 422 rather
        than emit a broken Invoice row."""
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])

        r = test_client.post(
            "/ocr/invoice",
            headers=_auth_headers(token),
            data={"direction": "purchase", "gstin_profile_id": str(gpid)},
            files={"file": ("mystery.pdf", b"not a known fixture", "application/pdf")},
        )
        assert r.status_code == 201
        ocr_id = r.json()["id"]

        r_accept = test_client.post(
            f"/ocr/extractions/{ocr_id}/accept",
            headers=_auth_headers(token),
            json={},
        )
        assert r_accept.status_code == 422
        detail = r_accept.json()["detail"]
        assert detail["error"] == "ocr_missing_required_fields"
        assert "supplier_gstin" in detail["missing"]

        # Row remains draft (accept was rejected before status flipped).
        with owner_engine.begin() as conn:
            row_status = conn.execute(
                text("SELECT status FROM ocr_extraction WHERE id = :i"),
                {"i": ocr_id},
            ).scalar()
        assert row_status == "draft"


class TestRejectExtraction:
    def test_reject_transitions_status_no_invoice(
        self,
        test_client,
        bootstrap_firm,
        pdfminer_invoice_pdf: bytes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "ocr_mode", "pdfminer")
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])

        ocr_id = _post_pdfminer_extraction(
            test_client, token, gpid, pdfminer_invoice_pdf
        )

        r = test_client.post(
            f"/ocr/extractions/{ocr_id}/reject",
            headers=_auth_headers(token),
            json={"reason": "wrong client — belongs to another firm"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"

        with owner_engine.begin() as conn:
            ocr = conn.execute(
                text(
                    "SELECT status, invoice_id, decided_by "
                    "FROM ocr_extraction WHERE id = :i"
                ),
                {"i": str(ocr_id)},
            ).mappings().first()
            assert ocr["status"] == "rejected"
            assert ocr["invoice_id"] is None
            assert uuid.UUID(str(ocr["decided_by"])) == admin["user_id"]

            audits = conn.execute(
                text(
                    "SELECT diff FROM audit_log "
                    "WHERE firm_id = :fid AND action = 'ocr.rejected' "
                    "AND entity_id = :i"
                ),
                {"fid": str(admin["firm_id"]), "i": str(ocr_id)},
            ).fetchall()
            assert len(audits) == 1

    def test_reject_after_accept_returns_409(
        self,
        test_client,
        bootstrap_firm,
        pdfminer_invoice_pdf: bytes,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "ocr_mode", "pdfminer")
        admin = bootstrap_firm()
        token = _login(test_client, admin)
        gpid = _seed_gstin(admin["firm_id"])

        ocr_id = _post_pdfminer_extraction(
            test_client, token, gpid, pdfminer_invoice_pdf
        )
        # Accept first.
        r1 = test_client.post(
            f"/ocr/extractions/{ocr_id}/accept",
            headers=_auth_headers(token),
            json={},
        )
        assert r1.status_code == 200
        # Reject on an accepted row → 409.
        r2 = test_client.post(
            f"/ocr/extractions/{ocr_id}/reject",
            headers=_auth_headers(token),
            json={"reason": "changed my mind"},
        )
        assert r2.status_code == 409
