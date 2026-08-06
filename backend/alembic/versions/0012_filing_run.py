"""filing_run — persisted GSTR-1 / GSTR-3B JSON payloads

Revision ID: 0012_filing_run
Revises: 0011_supplier_contact
Create Date: 2026-08-06

Introduces the artifact table that holds the JSON payload we would
upload to GSTN for a given (gstin, period, return_type). Each row is
one "draft" — regenerating overwrites the payload for that triple
rather than accumulating history (CA can regenerate freely without
littering the table). Once the CA approves + files, status flips to
``approved`` then ``filed`` and the payload becomes immutable at the
service layer.

RLS mirrors every other tenant table: firm_id scoped, forced.
"""
from __future__ import annotations

from alembic import op


revision = "0012_filing_run"
down_revision = "0011_supplier_contact"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    op.execute("CREATE TYPE filing_status AS ENUM ('draft', 'approved', 'filed');")
    op.execute(
        """
        CREATE TABLE filing_run (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE RESTRICT,
            gstin_profile_id UUID NOT NULL
                REFERENCES gstin_profile(id) ON DELETE CASCADE,
            return_type return_type NOT NULL,
            period TEXT NOT NULL,
            status filing_status NOT NULL DEFAULT 'draft',
            payload JSONB NOT NULL,
            rule_pack_version TEXT NOT NULL,
            generated_by UUID
                REFERENCES app_user(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            -- Only one live draft per (gid, period, return_type). Regenerate
            -- updates in place; a re-file after approval must be a new row
            -- (deferred until we track amendments — for now the CA re-drafts
            -- by resetting status).
            CONSTRAINT filing_run_gid_period_return_uniq
                UNIQUE (gstin_profile_id, period, return_type),
            CONSTRAINT filing_run_period_yyyymm CHECK (period ~ '^[0-9]{6}$')
        );
        """
    )
    op.execute(
        "CREATE INDEX filing_run_firm_period_idx "
        "ON filing_run (firm_id, period);"
    )

    op.execute("ALTER TABLE filing_run ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE filing_run FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY filing_run_firm_isolation ON filing_run
        USING (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        )
        WITH CHECK (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        );
        """
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON filing_run TO {APP_ROLE};"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS filing_run CASCADE;")
    op.execute("DROP TYPE IF EXISTS filing_status;")
