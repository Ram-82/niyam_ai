"""user_invite table + app_user.last_login_at

Revision ID: 0002_user_invite_and_last_login
Revises: 0001_initial
Create Date: 2026-07-14

Adds two things the auth stack (Step 3) needs:

* ``user_invite`` — firm-scoped invite tokens issued by admins. Tenant table
  with the same RLS/FORCE policy shape as every other tenant table in
  ``0001_initial``. ``token_hash`` stores the SHA-256 of the raw token so a
  DB dump does not leak the invite; the raw token is shown once at creation
  and then discarded. GRANTs match the other read/write tenant tables.

* ``app_user.last_login_at`` — nullable timestamptz. Written by the login
  handler after a successful password + TOTP round trip. Used by the
  dashboard to surface inactive accounts and to power the /me payload.

Design notes:

* Same policy shape as the initial migration:
  ``firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid``.
  The NULLIF wrapper is the safe-fail path when a request forgets to pin the
  GUC or accidentally pins it to the empty string.
* ``token_hash`` is UNIQUE globally (not just per firm). Callers look up the
  invite by hash during registration before the firm scope is known.
"""
from __future__ import annotations

from alembic import op


revision = "0002_user_invite_and_last_login"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. app_user.last_login_at
    # ------------------------------------------------------------------
    op.execute(
        "ALTER TABLE app_user ADD COLUMN last_login_at TIMESTAMPTZ;"
    )

    # ------------------------------------------------------------------
    # 2. user_invite table
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE user_invite (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL REFERENCES ca_firm(id) ON DELETE CASCADE,
            email CITEXT NOT NULL,
            role user_role NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            invited_by UUID REFERENCES app_user(id) ON DELETE SET NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            accepted_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX user_invite_firm_email_idx "
        "ON user_invite (firm_id, email);"
    )

    # ------------------------------------------------------------------
    # 3. RLS policy — same shape as every other tenant table.
    # ------------------------------------------------------------------
    op.execute("ALTER TABLE user_invite ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE user_invite FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY user_invite_firm_isolation ON user_invite
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

    # ------------------------------------------------------------------
    # 4. Grants: read/write for the app role, matching the other tenant tables.
    # ------------------------------------------------------------------
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON user_invite TO {APP_ROLE};"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_invite CASCADE;")
    op.execute("ALTER TABLE app_user DROP COLUMN IF EXISTS last_login_at;")
