"""user_firm_membership + 1:1 backfill (Phase 2 — multi-firm auth).

Revision ID: 0025_user_firm_membership
Revises: 0024_narrator_cost_and_budget
Create Date: 2026-08-26

Introduces per-user, per-firm role assignment so a partner in multiple
CA firms can hold ONE :class:`app_user` row and multiple memberships.

Load-bearing invariants — a mistake here is a cross-tenant data leak:

* One row per (user_id, firm_id) — enforced by unique index. A user
  cannot appear twice in the same firm even by a race.
* RLS on ``firm_id`` matches every other tenant table's pattern, with
  both ``USING`` and ``WITH CHECK``. The auth layer, which needs to
  read all of a user's memberships (spanning firms) at login time,
  uses ``owner_session()`` — not the app role — for that scan.
* Backfill is idempotent (``ON CONFLICT DO NOTHING``) and asserts a
  post-condition (membership count == pre-migration user count) so a
  botched re-run cannot silently drop rows.
* Role uses the existing ``user_role`` enum (admin | staff). Spec
  says: "Do not invent a permission matrix beyond what existing
  endpoints already distinguish" (P3_BUILD_PROMPT §4).

Downgrade drops the table; the ``app_user.firm_id`` column and every
1:1 assumption in the app code path remain intact, so a rollback here
is a rollback of the *membership plumbing*, not of tenant assignment.
"""
from __future__ import annotations

from alembic import op
from sqlalchemy import text


revision = "0025_user_firm_membership"
down_revision = "0024_narrator_cost_and_budget"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE user_firm_membership (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL
                REFERENCES app_user(id) ON DELETE CASCADE,
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE CASCADE,
            -- Uses the existing user_role enum (admin | staff). Per-firm
            -- role: a user may be admin in firm A and staff in firm B.
            role user_role NOT NULL,
            -- 'active' | 'invited' | 'suspended'. Suspended blocks
            -- issuing a token with this firm as active, without
            -- deleting the row (audit + rejoin path preserved).
            status TEXT NOT NULL DEFAULT 'active',
            invited_by UUID REFERENCES app_user(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT user_firm_membership_status_ok CHECK (
                status IN ('active', 'invited', 'suspended')
            )
        );
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX user_firm_membership_user_firm_uniq "
        "ON user_firm_membership (user_id, firm_id);"
    )
    op.execute(
        "CREATE INDEX user_firm_membership_firm_role "
        "ON user_firm_membership (firm_id, role, status);"
    )
    op.execute(
        "CREATE INDEX user_firm_membership_user "
        "ON user_firm_membership (user_id);"
    )

    # RLS — matches every other tenant table's pattern. A caller with
    # active firm A sees only their firm-A memberships. Auth code that
    # needs the full membership set for a user (login, firm-switch)
    # runs via owner_session() — see app.auth flows.
    op.execute("ALTER TABLE user_firm_membership ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE user_firm_membership FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY user_firm_membership_firm_isolation
        ON user_firm_membership
        USING (
            firm_id
            = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        )
        WITH CHECK (
            firm_id
            = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        );
        """
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON user_firm_membership TO {APP_ROLE};"
    )

    # -----------------------------------------------------------------
    # Auto-membership trigger — every INSERT on app_user creates a
    # matching user_firm_membership row (user + home firm, same role,
    # active). Makes the invariant "every user has at least one
    # membership" a DB constraint rather than a caller responsibility.
    # Backfill below is still needed for pre-existing rows; the
    # trigger only fires on future INSERTs.
    # -----------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION niyam_app_user_ensure_membership()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            INSERT INTO user_firm_membership (
                user_id, firm_id, role, status
            ) VALUES (
                NEW.id, NEW.firm_id, NEW.role, 'active'
            )
            ON CONFLICT (user_id, firm_id) DO NOTHING;
            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER app_user_auto_membership
        AFTER INSERT ON app_user
        FOR EACH ROW EXECUTE FUNCTION niyam_app_user_ensure_membership();
        """
    )

    # -----------------------------------------------------------------
    # Backfill — one membership row per existing app_user, using their
    # current firm_id + role. Idempotent via the unique index.
    # -----------------------------------------------------------------
    conn = op.get_bind()
    pre_user_count = conn.execute(
        text("SELECT COUNT(*) FROM app_user")
    ).scalar_one()
    conn.execute(
        text(
            """
            INSERT INTO user_firm_membership
                (user_id, firm_id, role, status, created_at)
            SELECT id, firm_id, role, 'active', created_at
            FROM app_user
            ON CONFLICT (user_id, firm_id) DO NOTHING;
            """
        )
    )
    post_membership_count = conn.execute(
        text(
            "SELECT COUNT(*) FROM user_firm_membership WHERE status = 'active'"
        )
    ).scalar_one()

    # Post-conditions per spec §4. Loud failure on drift.
    if post_membership_count < pre_user_count:
        raise RuntimeError(
            f"user_firm_membership backfill dropped rows: "
            f"pre-user={pre_user_count}, post-membership={post_membership_count}"
        )
    orphan_count = conn.execute(
        text(
            """
            SELECT COUNT(*) FROM app_user u
            WHERE NOT EXISTS (
                SELECT 1 FROM user_firm_membership m
                WHERE m.user_id = u.id AND m.firm_id = u.firm_id
            )
            """
        )
    ).scalar_one()
    if orphan_count > 0:
        raise RuntimeError(
            f"user_firm_membership backfill left {orphan_count} orphan users"
        )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS app_user_auto_membership ON app_user;"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS niyam_app_user_ensure_membership();"
    )
    op.execute("DROP TABLE IF EXISTS user_firm_membership CASCADE;")
