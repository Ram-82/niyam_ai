"""reminder_log — one row per emitted due-date reminder

Revision ID: 0014_reminder_log
Revises: 0013_password_reset
Create Date: 2026-08-06

The unique constraint on
(gstin_profile_id, period, return_type, days_before_due, channel,
 recipient_user_id)
is the idempotency guarantee: re-running the sweep for the same day
after a crash or double-fire cannot double-email a recipient. The
sweep issues an INSERT ... ON CONFLICT DO NOTHING and only dispatches
the email when rowcount == 1.

``days_before_due`` is signed: 7/3/1/0 are the pre-due thresholds; a
future overdue-nudge phase can use negative values.

RLS mirrors every tenant table — firm_id policy, forced.
"""
from __future__ import annotations

from alembic import op


revision = "0014_reminder_log"
down_revision = "0013_password_reset"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE reminder_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE CASCADE,
            gstin_profile_id UUID NOT NULL
                REFERENCES gstin_profile(id) ON DELETE CASCADE,
            period TEXT NOT NULL,
            return_type return_type NOT NULL,
            days_before_due INTEGER NOT NULL,
            channel TEXT NOT NULL,
            recipient_user_id UUID NOT NULL
                REFERENCES app_user(id) ON DELETE CASCADE,
            recipient_email TEXT NOT NULL,
            sent_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT reminder_log_idempotency UNIQUE (
                gstin_profile_id, period, return_type,
                days_before_due, channel, recipient_user_id
            ),
            CONSTRAINT reminder_log_period_yyyymm CHECK (period ~ '^[0-9]{6}$')
        );
        """
    )
    op.execute(
        "CREATE INDEX reminder_log_firm_period_idx "
        "ON reminder_log (firm_id, period);"
    )

    op.execute("ALTER TABLE reminder_log ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE reminder_log FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY reminder_log_firm_isolation ON reminder_log
        USING (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        )
        WITH CHECK (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        );
        """
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON reminder_log TO {APP_ROLE};"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS reminder_log CASCADE;")
