"""password_reset — one-shot self-service password reset tokens

Revision ID: 0013_password_reset
Revises: 0012_filing_run
Create Date: 2026-08-06

Mirrors the ``user_invite`` shape: one row per issued reset token,
``token_hash`` is a SHA-256 of the raw URL-safe token (never persisted
in the clear), single-use enforced at the service layer via ``used_at``.

RLS scoped to firm_id like every other tenant table, so a compromised
one-firm session cannot enumerate reset attempts from another firm.
"""
from __future__ import annotations

from alembic import op


revision = "0013_password_reset"
down_revision = "0012_filing_run"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    # ``password_changed_at`` is stamped whenever the password_hash is
    # updated. The refresh endpoint rejects any refresh JWT whose iat
    # predates this timestamp, so a password reset immediately kills
    # every outstanding refresh token for the user.
    op.execute(
        "ALTER TABLE app_user ADD COLUMN password_changed_at TIMESTAMPTZ "
        "NOT NULL DEFAULT now();"
    )

    op.execute(
        """
        CREATE TABLE password_reset (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE CASCADE,
            user_id UUID NOT NULL
                REFERENCES app_user(id) ON DELETE CASCADE,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ,
            requester_ip TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX password_reset_user_idx ON password_reset (user_id);"
    )

    op.execute("ALTER TABLE password_reset ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE password_reset FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY password_reset_firm_isolation ON password_reset
        USING (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        )
        WITH CHECK (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        );
        """
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON password_reset TO {APP_ROLE};"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS password_reset CASCADE;")
    op.execute("ALTER TABLE app_user DROP COLUMN IF EXISTS password_changed_at;")
