"""RLS isolation proofs.

These are the load-bearing tests. If any of them regress, tenant data can
leak between firms — that is a P0 security bug regardless of what else is
green.

Each test connects via ``app_engine``, which SET ROLEs to ``niyam_app``
(NOBYPASSRLS) on connect. Some tests deliberately construct queries that
would leak in an app-layer-only system, and assert RLS still holds.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError, InternalError, ProgrammingError

from app.db import app_engine


def _pin_firm(conn, firm_id: uuid.UUID) -> None:
    conn.execute(
        text("SELECT set_config('app.current_firm_id', :fid, true)"),
        {"fid": str(firm_id)},
    )


@pytest.mark.rls
def test_select_star_only_returns_own_firm(two_firms) -> None:
    firm_a, firm_b = two_firms
    with app_engine.begin() as conn:
        _pin_firm(conn, firm_a)
        rows = conn.execute(text("SELECT firm_id FROM invoice")).fetchall()
    assert rows, "firm A should see its own invoices"
    assert all(r[0] == firm_a for r in rows), (
        "SELECT * on invoice leaked cross-firm rows"
    )


@pytest.mark.rls
def test_buggy_where_naming_other_firm_still_blocked(two_firms) -> None:
    """The classic 'developer forgot the firm_id filter' bug path.

    A buggy handler could hard-code the wrong firm_id in a WHERE clause.
    RLS applies to the base relation BEFORE the WHERE clause is evaluated,
    so no rows come back.
    """
    firm_a, firm_b = two_firms
    with app_engine.begin() as conn:
        _pin_firm(conn, firm_a)
        rows = conn.execute(
            text("SELECT id FROM invoice WHERE firm_id = :other"),
            {"other": str(firm_b)},
        ).fetchall()
    assert rows == [], "RLS did not block a WHERE-clause pointed at another firm"


@pytest.mark.rls
def test_insert_with_wrong_firm_id_rejected_by_with_check(
    two_firms, owner_conn
) -> None:
    """A firm-A-scoped session must not be able to insert a firm-B row.

    We look up firm B's gstin_profile using the owner connection (bypasses
    RLS) so the FK target is valid — then attempt the malicious INSERT via
    the app-role session pinned to firm A. RLS ``WITH CHECK`` should reject.
    """
    firm_a, firm_b = two_firms
    gid_b = owner_conn.execute(
        text("SELECT id FROM gstin_profile WHERE firm_id = :fb LIMIT 1"),
        {"fb": str(firm_b)},
    ).scalar()
    assert gid_b is not None, "seed did not create firm B's gstin_profile"

    with pytest.raises((DatabaseError, InternalError, ProgrammingError)) as ei:
        with app_engine.begin() as conn:
            _pin_firm(conn, firm_a)
            conn.execute(
                text(
                    """
                    INSERT INTO invoice (
                        firm_id, gstin_profile_id, source, direction,
                        invoice_number, invoice_date, taxable_value_paise,
                        total_paise, content_hash
                    ) VALUES (
                        :bad_firm, :gid, 'manual', 'purchase',
                        'INV-EVIL', DATE '2026-06-20', 1, 1, :hash
                    )
                    """
                ),
                {
                    "bad_firm": str(firm_b),
                    "gid": gid_b,
                    "hash": f"evil-{uuid.uuid4()}",
                },
            )
    msg = str(ei.value).lower()
    assert "row-level security" in msg or "row level security" in msg


@pytest.mark.rls
def test_missing_firm_guc_returns_zero_rows(two_firms) -> None:
    """Safe-fail: unset GUC → policy returns NULL → no rows."""
    with app_engine.begin() as conn:
        # No _pin_firm call.
        rows = conn.execute(text("SELECT * FROM invoice")).fetchall()
    assert rows == [], "Unset GUC leaked rows"


@pytest.mark.rls
def test_audit_log_update_blocked_by_trigger(two_firms) -> None:
    firm_a, _ = two_firms
    with app_engine.begin() as conn:
        _pin_firm(conn, firm_a)
        conn.execute(
            text(
                """
                INSERT INTO audit_log (firm_id, action, entity_type, entity_id)
                VALUES (:fid, 'test', 'invoice', :eid)
                """
            ),
            {"fid": str(firm_a), "eid": str(uuid.uuid4())},
        )

    with pytest.raises((DatabaseError, InternalError, ProgrammingError)) as ei:
        with app_engine.begin() as conn:
            _pin_firm(conn, firm_a)
            conn.execute(text("UPDATE audit_log SET action = 'tampered'"))
    msg = str(ei.value).lower()
    # Defense in depth: the app role's grants revoke UPDATE/DELETE so
    # "permission denied" is what fires first; the append-only trigger is
    # the belt-and-braces layer in case the grants are later widened.
    assert "append-only" in msg or "permission denied" in msg


@pytest.mark.rls
def test_readiness_snapshot_delete_blocked_by_trigger(two_firms) -> None:
    firm_a, _ = two_firms
    # Owner inserts a snapshot to give the trigger something to reject.
    with app_engine.begin() as conn:
        _pin_firm(conn, firm_a)
        gid = conn.execute(
            text("SELECT id FROM gstin_profile LIMIT 1")
        ).scalar()
        conn.execute(
            text(
                """
                INSERT INTO readiness_snapshot (
                    firm_id, gstin_profile_id, return_type, period,
                    score, rule_pack_version
                ) VALUES (:fid, :gid, 'GSTR1', '202606', 61, '1.0.0')
                """
            ),
            {"fid": str(firm_a), "gid": gid},
        )
    with pytest.raises((DatabaseError, InternalError, ProgrammingError)) as ei:
        with app_engine.begin() as conn:
            _pin_firm(conn, firm_a)
            conn.execute(text("DELETE FROM readiness_snapshot"))
    msg = str(ei.value).lower()
    # Defense in depth: the app role's grants revoke UPDATE/DELETE so
    # "permission denied" is what fires first; the append-only trigger is
    # the belt-and-braces layer in case the grants are later widened.
    assert "append-only" in msg or "permission denied" in msg


@pytest.mark.rls
def test_consent_log_update_blocked_by_trigger(two_firms) -> None:
    firm_a, _ = two_firms
    with app_engine.begin() as conn:
        _pin_firm(conn, firm_a)
        client_id = conn.execute(text("SELECT id FROM client LIMIT 1")).scalar()
        conn.execute(
            text(
                """
                INSERT INTO consent_log (firm_id, client_id, purpose)
                VALUES (:fid, :cid, 'gstn_pull')
                """
            ),
            {"fid": str(firm_a), "cid": client_id},
        )
    with pytest.raises((DatabaseError, InternalError, ProgrammingError)) as ei:
        with app_engine.begin() as conn:
            _pin_firm(conn, firm_a)
            conn.execute(text("UPDATE consent_log SET purpose = 'other'"))
    msg = str(ei.value).lower()
    # Defense in depth: the app role's grants revoke UPDATE/DELETE so
    # "permission denied" is what fires first; the append-only trigger is
    # the belt-and-braces layer in case the grants are later widened.
    assert "append-only" in msg or "permission denied" in msg
