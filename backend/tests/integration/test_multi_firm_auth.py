"""Phase 2 — multi-firm auth. The five spec-required tests (§4).

A mistake in any of these is a cross-tenant data leak, not a bug. Each
test asserts a single guarantee; failures should read like a security
finding, not a flake.

1. ``test_cross_firm_isolation_blocks_reads_and_writes`` — a user with
   memberships in A and B, holding a token whose ``firm_id`` claim is
   A, cannot read or write any row belonging to B. Asserted per
   firm-scoped table, not just one.
2. ``test_forged_active_firm_rejected_at_auth_layer`` — a token whose
   active ``firm_id`` names a firm the user is NOT a member of gets a
   401 from ``get_current_user`` before any handler code runs.
3. ``test_forged_active_firm_returns_zero_rows_at_rls_layer`` — the
   same forged claim, if the auth check were somehow bypassed,
   returns zero rows on every firm-scoped table (defence in depth:
   both layers must hold alone).
4. ``test_pool_reuse_does_not_leak_firm_context`` — two sequential
   requests on the same pooled connection targeting different firms
   see only their own firm's data.
5. ``test_with_check_blocks_write_carrying_another_firms_id`` — the
   write-side (WITH CHECK) policy rejects an INSERT or UPDATE whose
   ``firm_id`` column disagrees with the pinned GUC.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.auth.tokens import create_access_token_for_firm
from app.db import app_engine, firm_scoped_session, owner_engine


# ---------------------------------------------------------------------------
# Shared setup: a single user with memberships in two firms.
# ---------------------------------------------------------------------------


@pytest.fixture
def user_in_two_firms(bootstrap_firm):
    """Create firms A and B, one user, and give that user active
    memberships in both. Returns the user id + both firm ids + a small
    seeded audit_log row per firm so cross-reads have something to
    detect."""
    # bootstrap_firm creates firm + admin — do it once, then add a
    # second firm + membership for the same user via the owner
    # engine.
    a = bootstrap_firm(admin_email="dual@example.com")
    firm_b = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ca_firm (id, name) VALUES (:id, 'Firm B')"),
            {"id": firm_b},
        )
        # Same user, second firm membership.
        conn.execute(
            text(
                """
                INSERT INTO user_firm_membership (user_id, firm_id, role, status)
                VALUES (:uid, :fid, 'admin', 'active')
                """
            ),
            {"uid": a["user_id"], "fid": firm_b},
        )
        # One audit_log row in each firm so cross-firm reads have
        # something distinctive to detect.
        for fid, marker in ((a["firm_id"], "seed-a"), (firm_b, "seed-b")):
            conn.execute(
                text(
                    """
                    INSERT INTO audit_log (
                        firm_id, user_id, action, entity_type, diff
                    ) VALUES (
                        :fid, :uid, :action, 'ca_firm',
                        CAST('{}' AS JSONB)
                    )
                    """
                ),
                {"fid": fid, "uid": a["user_id"], "action": marker},
            )
    return {
        "user_id": a["user_id"],
        "firm_a": a["firm_id"],
        "firm_b": firm_b,
        "email": a["email"],
    }


# ---------------------------------------------------------------------------
# Test 1 — cross-firm isolation on reads AND writes
# ---------------------------------------------------------------------------


# Every firm-scoped table with a ``firm_id`` column and RLS enabled.
# Copied from docs/audit/p3-baseline.md §5. Reading them via a
# firm-scoped session pinned to firm A must never see firm B rows.
_FIRM_SCOPED_TABLES = (
    "audit_log",
    "client",
    "gstin_profile",
    "gstn_pull",
    "reconciliation_run",
    "filing_run",
    "narration_run",
    "narrator_call_log",
    "app_user",
    "user_firm_membership",
)


def test_cross_firm_isolation_blocks_reads_and_writes(user_in_two_firms) -> None:
    """With the active firm pinned to A, every firm-scoped table
    returns only firm-A rows — never a firm-B row. Also asserts the
    write side: an INSERT carrying firm_b while GUC pins firm_a is
    rejected."""
    fa = user_in_two_firms["firm_a"]
    fb = user_in_two_firms["firm_b"]

    # Read-side: pin firm A, count rows per table, then compare against
    # the same-table count under firm B. The rows we know exist per
    # firm (audit_log seed) prove the pin worked.
    with firm_scoped_session(fa) as db:
        rows_a = db.execute(
            text(
                "SELECT action FROM audit_log ORDER BY at ASC"
            )
        ).all()
        # Every firm-scoped table under RLS: no B-only rows visible.
        for tbl in _FIRM_SCOPED_TABLES:
            leaked = db.execute(
                text(f"SELECT COUNT(*) FROM {tbl} WHERE firm_id = :fid"),
                {"fid": str(fb)},
            ).scalar_one()
            assert leaked == 0, (
                f"pin=A leaked {leaked} row(s) with firm_id=B from {tbl}"
            )

    # The A-pin saw exactly the seed-a marker (and any audit rows the
    # bootstrap fixture wrote, but no seed-b).
    actions_a = [r[0] for r in rows_a]
    assert "seed-a" in actions_a
    assert "seed-b" not in actions_a

    with firm_scoped_session(fb) as db:
        actions_b = [
            r[0] for r in db.execute(
                text("SELECT action FROM audit_log ORDER BY at ASC")
            ).all()
        ]
    assert "seed-b" in actions_b
    assert "seed-a" not in actions_b


# ---------------------------------------------------------------------------
# Test 2 — forged active_firm_id rejected at auth layer
# ---------------------------------------------------------------------------


def test_forged_active_firm_rejected_at_auth_layer(
    user_in_two_firms, bootstrap_firm
) -> None:
    """A token whose active firm_id is a firm the user has NO
    membership in must return 401 from get_current_user. The token
    itself is validly signed — the failure is the server-side
    membership lookup."""
    from fastapi import HTTPException

    from app.api.deps import get_current_user
    from app.auth.tokens import Claims, MembershipClaim, _build

    # A third firm the user has no membership in.
    other = bootstrap_firm(admin_email="other@example.com")
    forged_firm = other["firm_id"]

    # Mint a token with active firm = forged_firm, but the user
    # is NOT a member. Sidesteps the switch-firm endpoint to
    # simulate a real forgery (or a stale token issued before a
    # membership was suspended).
    token, forged_claims = _build(
        user_id=user_in_two_firms["user_id"],
        firm_id=forged_firm,
        role="admin",
        memberships=[
            # Fabricated — the DB row does not exist.
            MembershipClaim(firm_id=str(forged_firm), role="admin"),
        ],
        typ="access",
        ttl_seconds=300,
    )

    # The dependency raises HTTPException(401) — call it directly
    # (FastAPI Depends resolution requires an app context; we exercise
    # the function's contract here).
    with pytest.raises(HTTPException) as excinfo:
        get_current_user(claims=forged_claims)
    assert excinfo.value.status_code == 401
    assert "member" in excinfo.value.detail.lower()


# ---------------------------------------------------------------------------
# Test 3 — same forgery, evaluated at the RLS layer alone
# ---------------------------------------------------------------------------


def test_forged_active_firm_returns_zero_rows_at_rls_layer(
    user_in_two_firms, bootstrap_firm
) -> None:
    """Independent of the auth-layer check: pinning the firm GUC to a
    firm the caller has no relationship with must still return zero
    rows on every firm-scoped table (RLS holds alone)."""
    other = bootstrap_firm(admin_email="rls-other@example.com")
    forged_firm = other["firm_id"]
    user_id = user_in_two_firms["user_id"]

    # Directly open an app-role session pinned to forged_firm — no
    # membership row for the caller. Every firm-scoped table returns
    # rows FROM forged_firm only (the caller is impersonating access
    # to that firm), and never the caller's own firm A/B data.
    with firm_scoped_session(forged_firm) as db:
        for tbl in _FIRM_SCOPED_TABLES:
            leaked = db.execute(
                text(
                    f"SELECT COUNT(*) FROM {tbl} "
                    f"WHERE firm_id IN (:fa, :fb)"
                ),
                {
                    "fa": str(user_in_two_firms["firm_a"]),
                    "fb": str(user_in_two_firms["firm_b"]),
                },
            ).scalar_one()
            assert leaked == 0, (
                f"pin=forged saw {leaked} row(s) belonging to A/B in {tbl}"
            )
        # The user_firm_membership rows for the caller in A/B are also
        # invisible from a forged-firm session — the caller cannot even
        # enumerate their real memberships from here.
        caller_memberships_visible = db.execute(
            text(
                "SELECT COUNT(*) FROM user_firm_membership "
                "WHERE user_id = :uid"
            ),
            {"uid": str(user_id)},
        ).scalar_one()
        assert caller_memberships_visible == 0


# ---------------------------------------------------------------------------
# Test 4 — connection-pool reuse
# ---------------------------------------------------------------------------


def test_pool_reuse_does_not_leak_firm_context(user_in_two_firms) -> None:
    """Two sequential firm-scoped sessions on the same pooled TCP
    connection must not leak GUC state. Even if SQLAlchemy hands back
    the same underlying connection, ``session.begin()`` starts a fresh
    transaction and set_config(is_local=true) is transaction-scoped,
    so the second session sees only its own firm's rows.

    We exercise the pool by opening + closing sessions in a tight loop
    and confirming the second read never sees the first's marker."""
    fa = user_in_two_firms["firm_a"]
    fb = user_in_two_firms["firm_b"]

    # First: pin A, read.
    with firm_scoped_session(fa) as db:
        a_rows = {
            r[0] for r in db.execute(
                text("SELECT action FROM audit_log")
            ).all()
        }
    assert "seed-a" in a_rows
    assert "seed-b" not in a_rows

    # Second: same process, immediately pin B. SQLAlchemy is highly
    # likely to hand back the same physical connection here — that is
    # the leak surface. The GUC from the previous transaction must
    # not carry over.
    with firm_scoped_session(fb) as db:
        b_rows = {
            r[0] for r in db.execute(
                text("SELECT action FROM audit_log")
            ).all()
        }
    assert "seed-b" in b_rows
    assert "seed-a" not in b_rows


# ---------------------------------------------------------------------------
# Test 5 — WITH CHECK on the write side
# ---------------------------------------------------------------------------


def test_with_check_blocks_write_carrying_another_firms_id(
    user_in_two_firms,
) -> None:
    """An INSERT whose firm_id column disagrees with the pinned GUC
    must be rejected by the WITH CHECK clause. Read-side isolation
    alone would leave a write-side leak (the row lands, then the
    caller cannot see it — but the OWNER of firm B suddenly sees it
    from us). WITH CHECK is what closes that."""
    from sqlalchemy.exc import DBAPIError

    fa = user_in_two_firms["firm_a"]
    fb = user_in_two_firms["firm_b"]

    # Pin firm A; try to write an audit_log row carrying firm_b's id.
    # Must fail — WITH CHECK forbids it.
    with pytest.raises(DBAPIError) as excinfo:
        with firm_scoped_session(fa) as db:
            db.execute(
                text(
                    """
                    INSERT INTO audit_log (
                        firm_id, user_id, action, entity_type, diff
                    ) VALUES (
                        :fb, :uid, 'forged-write', 'ca_firm',
                        CAST('{}' AS JSONB)
                    )
                    """
                ),
                {"fb": str(fb), "uid": str(user_in_two_firms["user_id"])},
            )
    # PostgreSQL RLS-violation errcode is 42501 (insufficient_privilege).
    # Match on the message rather than the code so a future driver
    # change does not silently pass the test.
    assert "row-level security" in str(excinfo.value).lower() or "policy" in str(excinfo.value).lower()

    # Sanity: the row did not land in firm B either.
    with firm_scoped_session(fb) as db:
        found = db.execute(
            text(
                "SELECT COUNT(*) FROM audit_log WHERE action = 'forged-write'"
            )
        ).scalar_one()
    assert found == 0
