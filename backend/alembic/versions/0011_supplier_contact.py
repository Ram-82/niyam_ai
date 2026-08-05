"""supplier_contact — firm-scoped directory of supplier WhatsApp + email

Revision ID: 0011_supplier_contact
Revises: 0010_whatsapp_delivery
Create Date: 2026-08-05

Fixes the "CA types the supplier phone number every chase" pain point
introduced in commit bec861a. A single (firm, supplier_gstin) contact
row prefills the SupplierChasePanel modal so the CA only types once.

The directory is firm-scoped, NOT client-scoped: one supplier commonly
serves many clients of the same CA firm, and the contact info (phone,
email) belongs to the supplier, not to any single client relationship.
"""
from __future__ import annotations

from alembic import op


revision = "0011_supplier_contact"
down_revision = "0010_whatsapp_delivery"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE supplier_contact (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE RESTRICT,
            supplier_gstin TEXT NOT NULL,
            name TEXT NOT NULL,
            whatsapp_number TEXT,
            email TEXT,
            notes TEXT,
            created_by UUID
                REFERENCES app_user(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_by UUID
                REFERENCES app_user(id) ON DELETE SET NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT supplier_contact_firm_gstin_uniq
                UNIQUE (firm_id, supplier_gstin),
            -- Loose E.164 sanity: leading '+' + 8-15 digits. Meta rejects
            -- anything else at send time; we reject at write time so a
            -- typo does not linger in the directory. Nullable so a
            -- contact can be seeded with only an email.
            CONSTRAINT supplier_contact_whatsapp_e164 CHECK (
                whatsapp_number IS NULL
                OR whatsapp_number ~ '^\\+[1-9][0-9]{7,14}$'
            )
        );
        """
    )
    op.execute(
        "CREATE INDEX supplier_contact_firm_idx "
        "ON supplier_contact (firm_id);"
    )
    op.execute(
        "CREATE INDEX supplier_contact_gstin_lookup "
        "ON supplier_contact (firm_id, supplier_gstin);"
    )

    op.execute("ALTER TABLE supplier_contact ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE supplier_contact FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY supplier_contact_firm_isolation ON supplier_contact
        USING (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        )
        WITH CHECK (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        );
        """
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON supplier_contact TO {APP_ROLE};"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS supplier_contact CASCADE;")
