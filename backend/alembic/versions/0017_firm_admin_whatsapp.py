"""ca_firm.admin_whatsapp_number — E.164 number for automated WA notifications

Revision ID: 0017_firm_admin_whatsapp
Revises: 0016_firm_rule_pack
Create Date: 2026-08-10

Used by two automated (no-approval-gate) WhatsApp triggers:
  1. Reconciliation run complete — notify the CA admin.
  2. Due-date reminder sweep — notify the firm admin alongside the
     per-recipient email (the email goes to all admins + assigned staff;
     the WhatsApp goes to the one number set here).

NULL means no WhatsApp notification for this firm (opt-in via the
Settings UI).
"""
from __future__ import annotations

from alembic import op


revision = "0017_firm_admin_whatsapp"
down_revision = "0016_firm_rule_pack"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        r"""
        ALTER TABLE ca_firm
        ADD COLUMN admin_whatsapp_number TEXT
        CONSTRAINT ca_firm_admin_whatsapp_e164 CHECK (
            admin_whatsapp_number IS NULL
            OR admin_whatsapp_number ~ '^\+[1-9][0-9]{7,14}$'
        );
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ca_firm DROP COLUMN IF EXISTS admin_whatsapp_number;")
