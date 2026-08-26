"""Erasure mechanism: subject key wrap/unwrap/destroy + request lifecycle.

Covers ONLY the mechanism. Policy questions (who can request, when a
refusal is valid, which columns are actually encrypted with a subject
key) are out of scope — see docs/compliance/retention-and-erasure.md.

Does NOT go through the HTTP layer because there is no HTTP endpoint
by design.
"""
from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text

from app.db import AppSessionLocal, owner_engine
from app.erasure import keys as erasure_keys
from app.erasure import service as erasure_service
from app.erasure.keys import DEV_KEK_CHECKSUM, ErasureKekMissing, assert_kek_available


def _firm_scoped_session(firm_id: uuid.UUID):
    """Open a session with app.current_firm_id pinned. Mirrors
    ``_open_scoped_session`` in app/api/deps.py but returned as a context
    manager for direct test use."""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        session = AppSessionLocal()
        session.begin()
        try:
            session.execute(
                text(
                    "SELECT set_config('app.current_firm_id', :fid, true)"
                ),
                {"fid": str(firm_id)},
            )
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    return _cm()


def _make_firm() -> uuid.UUID:
    firm_id = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ca_firm (id, name) VALUES (:id, 'Erasure Firm')"),
            {"id": firm_id},
        )
    return firm_id


# ---------------------------------------------------------------------------
# Wrap / unwrap round trip
# ---------------------------------------------------------------------------


def test_allocate_and_unwrap_round_trip() -> None:
    firm_id = _make_firm()
    with _firm_scoped_session(firm_id) as session:
        row = erasure_keys.allocate(
            session, firm_id, "client", "client-ref-1"
        )
        subject_key = erasure_keys.unwrap(session, row.id)

    assert row.kek_version == 1
    assert len(subject_key) == 32
    assert not row.destroyed


def test_allocate_is_idempotent() -> None:
    firm_id = _make_firm()
    with _firm_scoped_session(firm_id) as session:
        a = erasure_keys.allocate(session, firm_id, "client", "same-ref")
    with _firm_scoped_session(firm_id) as session:
        b = erasure_keys.allocate(session, firm_id, "client", "same-ref")
    assert a.id == b.id


def test_destroy_zeroes_material_and_unwrap_fails() -> None:
    firm_id = _make_firm()
    with _firm_scoped_session(firm_id) as session:
        row = erasure_keys.allocate(
            session, firm_id, "supplier", "27ABCDE1111Z1Z1"
        )

    with _firm_scoped_session(firm_id) as session:
        erasure_keys.destroy(session, row.id)

    with _firm_scoped_session(firm_id) as session:
        with pytest.raises(ValueError):
            erasure_keys.unwrap(session, row.id)

    with owner_engine.begin() as conn:
        material, destroyed_at = conn.execute(
            text(
                "SELECT key_material, destroyed_at FROM subject_key "
                "WHERE id = :id"
            ),
            {"id": row.id},
        ).one()
    assert destroyed_at is not None
    assert bytes(material) == b"\x00"


def test_allocate_after_destroy_forbidden() -> None:
    firm_id = _make_firm()
    with _firm_scoped_session(firm_id) as session:
        row = erasure_keys.allocate(session, firm_id, "client", "shred-me")
    with _firm_scoped_session(firm_id) as session:
        erasure_keys.destroy(session, row.id)
    with _firm_scoped_session(firm_id) as session:
        with pytest.raises(ValueError):
            erasure_keys.allocate(session, firm_id, "client", "shred-me")


# ---------------------------------------------------------------------------
# Erasure request lifecycle
# ---------------------------------------------------------------------------


def test_create_then_execute_writes_audit_and_destroys_key() -> None:
    firm_id = _make_firm()
    with _firm_scoped_session(firm_id) as session:
        key = erasure_keys.allocate(session, firm_id, "client", "audit-me")
        req = erasure_service.create_request(
            session,
            firm_id=firm_id,
            subject_key_id=key.id,
            requested_by=None,
        )
    with _firm_scoped_session(firm_id) as session:
        erasure_service.execute_request(
            session, firm_id, req.id, executor_user_id=None
        )

    with owner_engine.begin() as conn:
        req_row = conn.execute(
            text(
                "SELECT status, executed_at FROM erasure_request "
                "WHERE id = :id"
            ),
            {"id": req.id},
        ).mappings().one()
        key_row = conn.execute(
            text("SELECT destroyed_at FROM subject_key WHERE id = :id"),
            {"id": key.id},
        ).mappings().one()
        audit_rows = conn.execute(
            text(
                "SELECT action FROM audit_log WHERE firm_id = :fid "
                "AND entity_type = 'erasure_request' ORDER BY at"
            ),
            {"fid": firm_id},
        ).scalars().all()
    assert req_row["status"] == "executed"
    assert req_row["executed_at"] is not None
    assert key_row["destroyed_at"] is not None
    assert list(audit_rows) == ["erasure.requested", "erasure.executed"]


def test_refuse_then_cannot_execute() -> None:
    firm_id = _make_firm()
    with _firm_scoped_session(firm_id) as session:
        key = erasure_keys.allocate(session, firm_id, "client", "refuse-me")
        req = erasure_service.create_request(
            session, firm_id, key.id, requested_by=None
        )
    with _firm_scoped_session(firm_id) as session:
        erasure_service.refuse_request(
            session, firm_id, req.id, None, "active tax proceedings"
        )
    with _firm_scoped_session(firm_id) as session:
        with pytest.raises(erasure_service.RequestNotPending):
            erasure_service.execute_request(session, firm_id, req.id, None)

    # Subject key must remain intact after a refusal.
    with _firm_scoped_session(firm_id) as session:
        material = erasure_keys.unwrap(session, key.id)
    assert len(material) == 32


def test_refuse_without_reason_rejected() -> None:
    firm_id = _make_firm()
    with _firm_scoped_session(firm_id) as session:
        key = erasure_keys.allocate(session, firm_id, "client", "no-reason")
        req = erasure_service.create_request(
            session, firm_id, key.id, requested_by=None
        )
    with _firm_scoped_session(firm_id) as session:
        with pytest.raises(ValueError):
            erasure_service.refuse_request(session, firm_id, req.id, None, "   ")


# ---------------------------------------------------------------------------
# RLS isolation
# ---------------------------------------------------------------------------


@pytest.mark.rls
def test_firm_cannot_see_other_firms_subject_keys() -> None:
    firm_a = _make_firm()
    firm_b = _make_firm()
    with _firm_scoped_session(firm_a) as session:
        row_a = erasure_keys.allocate(session, firm_a, "client", "a-client")
    with _firm_scoped_session(firm_b) as session:
        row_b = erasure_keys.allocate(session, firm_b, "client", "b-client")

    with _firm_scoped_session(firm_a) as session:
        rows_visible = session.execute(
            text("SELECT id FROM subject_key")
        ).scalars().all()
    ids = {str(r) for r in rows_visible}
    assert str(row_a.id) in ids
    assert str(row_b.id) not in ids, "RLS leak — firm A sees firm B's key"


# ---------------------------------------------------------------------------
# Append-only-ish: DELETE forbidden
# ---------------------------------------------------------------------------


def test_subject_key_delete_forbidden() -> None:
    firm_id = _make_firm()
    with _firm_scoped_session(firm_id) as session:
        row = erasure_keys.allocate(session, firm_id, "client", "no-delete")
    with owner_engine.begin() as conn:
        with pytest.raises(Exception) as ei:
            conn.execute(
                text("DELETE FROM subject_key WHERE id = :id"),
                {"id": row.id},
            )
        assert "mutation" in str(ei.value).lower()


def test_erasure_request_delete_forbidden() -> None:
    firm_id = _make_firm()
    with _firm_scoped_session(firm_id) as session:
        key = erasure_keys.allocate(session, firm_id, "client", "delete-req")
        req = erasure_service.create_request(
            session, firm_id, key.id, requested_by=None
        )
    with owner_engine.begin() as conn:
        with pytest.raises(Exception) as ei:
            conn.execute(
                text("DELETE FROM erasure_request WHERE id = :id"),
                {"id": req.id},
            )
        assert "mutation" in str(ei.value).lower()


# ---------------------------------------------------------------------------
# Constraint: terminal-consistency CHECK
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# KEK provenance + startup assertion (B2)
# ---------------------------------------------------------------------------


def test_allocated_key_records_dev_kek_checksum() -> None:
    """In mock mode the fallback dev KEK is used. Every wrapped row must
    carry that KEK's checksum so contamination is queryable."""
    firm_id = _make_firm()
    with _firm_scoped_session(firm_id) as session:
        row = erasure_keys.allocate(
            session, firm_id, "client", "checksum-me"
        )
    with owner_engine.begin() as conn:
        cks = conn.execute(
            text("SELECT kek_checksum FROM subject_key WHERE id = :id"),
            {"id": row.id},
        ).scalar_one()
    assert cks == DEV_KEK_CHECKSUM
    assert len(cks) == 16


def test_dev_kek_contamination_query() -> None:
    """The exact WHERE clause an operator would use to detect
    dev-KEK contamination in a real environment."""
    firm_id = _make_firm()
    with _firm_scoped_session(firm_id) as session:
        erasure_keys.allocate(session, firm_id, "client", "contam-1")
        erasure_keys.allocate(session, firm_id, "client", "contam-2")
    with owner_engine.begin() as conn:
        n = conn.execute(
            text(
                "SELECT COUNT(*) FROM subject_key "
                "WHERE firm_id = :fid AND kek_checksum = :cks"
            ),
            {"fid": firm_id, "cks": DEV_KEK_CHECKSUM},
        ).scalar_one()
    assert n == 2


def test_assert_kek_available_passes_in_mock_mode() -> None:
    """Mock mode + no ERASURE_KEK_KEYS env → dev fallback → OK."""
    from app.config import settings

    assert settings.gsp_mode == "mock", "test env should be mock"
    old = os.environ.pop("ERASURE_KEK_KEYS", None)
    try:
        assert_kek_available()  # must not raise
    finally:
        if old is not None:
            os.environ["ERASURE_KEK_KEYS"] = old


def test_assert_kek_available_raises_outside_mock_without_env(monkeypatch) -> None:
    """Non-mock mode + no ERASURE_KEK_KEYS env → refuse to start."""
    from app.config import settings

    monkeypatch.setattr(settings, "gsp_mode", "live")
    monkeypatch.delenv("ERASURE_KEK_KEYS", raising=False)
    with pytest.raises(ErasureKekMissing):
        assert_kek_available()


def test_assert_kek_available_accepts_env_outside_mock(monkeypatch) -> None:
    """Non-mock mode + valid ERASURE_KEK_KEYS env → OK."""
    import base64
    import secrets as _secrets

    from app.config import settings

    monkeypatch.setattr(settings, "gsp_mode", "live")
    real_kek = base64.urlsafe_b64encode(_secrets.token_bytes(32)).decode()
    monkeypatch.setenv("ERASURE_KEK_KEYS", f"1:{real_kek}")
    assert_kek_available()  # must not raise


def test_check_constraint_rejects_inconsistent_status() -> None:
    firm_id = _make_firm()
    with _firm_scoped_session(firm_id) as session:
        key = erasure_keys.allocate(session, firm_id, "client", "check-me")
    # Executed but no executed_at — must be rejected.
    with owner_engine.begin() as conn:
        with pytest.raises(Exception) as ei:
            conn.execute(
                text(
                    """
                    INSERT INTO erasure_request (
                        firm_id, subject_key_id, status
                    ) VALUES (
                        :fid, :sk, 'executed'
                    )
                    """
                ),
                {"fid": firm_id, "sk": key.id},
            )
        assert "erasure_request_terminal_consistency" in str(ei.value)
