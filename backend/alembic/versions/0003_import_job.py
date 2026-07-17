"""import_job: track file imports (invoices CSV/XLSX and GSTR-2B JSON)

Revision ID: 0003_import_job
Revises: 0002_user_invite_and_last_login
Create Date: 2026-07-14

Every upload creates one ``import_job`` row. A queued worker picks it up,
parses the file, normalizes to canonical invoices or B2B entries, and updates
the row's counts + status. Rejects are stored inline as JSONB so the errors
CSV endpoint can materialize on demand without extra storage.

Design notes:

* Kind and status are native Postgres enums so garbage values fail loud.
* ``gstin_profile_id`` is REQUIRED — an import always targets one GSTIN in a
  known return period. Cross-GSTIN files must be split client-side.
* ``rejected_rows_json`` is JSONB, capped by app-layer trimming (P1 stops
  storing after 10k rejects; the summary reports the true count). This
  avoids one bad 5MB CSV blowing up the row.
* Follows the same RLS shape as every other tenant table: firm-scoped
  policy on ``firm_id``, FORCE'd, grants match the other read/write tables.
"""
from __future__ import annotations

from alembic import op


revision = "0003_import_job"
down_revision = "0002_user_invite_and_last_login"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    op.execute(
        "CREATE TYPE import_kind AS ENUM ("
        "'purchase_csv', 'purchase_xlsx', 'sales_csv', 'sales_xlsx', 'gstr2b_json'"
        ");"
    )
    op.execute(
        "CREATE TYPE import_status AS ENUM ("
        "'queued', 'running', 'completed', 'failed'"
        ");"
    )

    op.execute(
        """
        CREATE TABLE import_job (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL REFERENCES ca_firm(id) ON DELETE RESTRICT,
            gstin_profile_id UUID NOT NULL
                REFERENCES gstin_profile(id) ON DELETE CASCADE,
            uploaded_by UUID REFERENCES app_user(id) ON DELETE SET NULL,
            kind import_kind NOT NULL,
            status import_status NOT NULL DEFAULT 'queued',
            filename TEXT NOT NULL,
            period TEXT,  -- 'YYYYMM' — meaningful for gstr2b_json
            total_rows INTEGER NOT NULL DEFAULT 0,
            accepted_rows INTEGER NOT NULL DEFAULT 0,
            rejected_rows INTEGER NOT NULL DEFAULT 0,
            duplicate_rows INTEGER NOT NULL DEFAULT 0,
            rejected_rows_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_message TEXT,
            uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            CONSTRAINT import_job_period_shape
                CHECK (period IS NULL OR period ~ '^[0-9]{6}$')
        );
        """
    )
    op.execute(
        "CREATE INDEX import_job_firm_time_idx "
        "ON import_job (firm_id, uploaded_at DESC);"
    )
    op.execute(
        "CREATE INDEX import_job_gstin_period_idx "
        "ON import_job (gstin_profile_id, kind, uploaded_at DESC);"
    )

    op.execute("ALTER TABLE import_job ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE import_job FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY import_job_firm_isolation ON import_job
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
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON import_job TO {APP_ROLE};"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS import_job CASCADE;")
    op.execute("DROP TYPE IF EXISTS import_status;")
    op.execute("DROP TYPE IF EXISTS import_kind;")
