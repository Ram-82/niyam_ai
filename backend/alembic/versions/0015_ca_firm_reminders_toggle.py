"""ca_firm.reminders_enabled — per-firm opt-out for the due-date sweep

Revision ID: 0015_ca_firm_reminders_toggle
Revises: 0014_reminder_log
Create Date: 2026-08-07

Default TRUE (opt-out model) so existing firms keep receiving nudges
once the global REMINDERS_ENABLED flag flips on. A firm admin can
disable via PATCH /firm/settings if their firm doesn't want the mail.
"""
from __future__ import annotations

from alembic import op


revision = "0015_ca_firm_reminders_toggle"
down_revision = "0014_reminder_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ca_firm ADD COLUMN reminders_enabled BOOLEAN "
        "NOT NULL DEFAULT TRUE;"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ca_firm DROP COLUMN IF EXISTS reminders_enabled;")
