"""subject_key + erasure_request — crypto-shredding mechanism (no policy).

Revision ID: 0023_subject_key_and_erasure
Revises: 0022_legal_acceptance
Create Date: 2026-08-19

Ships ONLY the mechanism, per the retention-and-erasure design doc.
* ``subject_key`` — per-subject symmetric key material, wrapped by an
  env-provisioned KEK. UPDATE is permitted (needed for
  ``destroyed_at`` set + key_material zero-overwrite). No append-only
  triggers.
* ``erasure_request`` — status-transition table, not append-only.

Neither table is wired into an end-user API yet. That is deliberate:
retention *periods* and erasure *scope* are policy questions the owner
must resolve with counsel + a CA before enabling an erasure endpoint
in production. See ``docs/compliance/retention-and-erasure.md``.

TODO-VERIFY-WITH-COUNSEL / TODO-VERIFY-WITH-OWNER markers in the design
doc must be resolved before any real subject data is written encrypted
to these key rows.
"""
from __future__ import annotations

from alembic import op


revision = "0023_subject_key_and_erasure"
down_revision = "0022_legal_acceptance"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    # -----------------------------------------------------------------
    # subject_key — wrapped per-subject symmetric key
    # -----------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE subject_key (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE RESTRICT,
            -- 'client' | 'supplier' | 'app_user'. Free-form so future
            -- subject kinds (e.g. 'partner') can land without a migration.
            subject_kind TEXT NOT NULL,
            -- Reference to the subject's row in its own table. TEXT so
            -- it can hold a UUID string (client.id, app_user.id) OR a
            -- GSTIN (supplier keys keyed by GSTIN).
            subject_ref TEXT NOT NULL,
            -- Wrapped key material. Format: KEK-envelope(nonce || key32).
            -- Zeroed on destruction (see destroyed_at).
            key_material BYTEA NOT NULL,
            -- KEK version at wrap time. Rotation seam mirrors gsp_session.
            kek_version INT NOT NULL,
            -- First 16 hex chars of SHA-256(kek_bytes). Lets us query for
            -- "which KEK actually wrapped this row" independent of the
            -- version integer — critical because a dev-fallback KEK
            -- contamination in a non-mock environment would otherwise be
            -- invisible: it too would carry ``kek_version = 1``. The
            -- dev-KEK checksum is a known constant, so a
            -- ``WHERE kek_checksum = '<dev-const>'`` query flags every
            -- contaminated row.
            kek_checksum TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            destroyed_at TIMESTAMPTZ,
            CONSTRAINT subject_key_kind_ok CHECK (
                subject_kind IN ('client', 'supplier', 'app_user')
            )
        );
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX subject_key_firm_subject_uniq "
        "ON subject_key (firm_id, subject_kind, subject_ref);"
    )
    op.execute(
        "CREATE INDEX subject_key_firm_kind "
        "ON subject_key (firm_id, subject_kind);"
    )
    op.execute("ALTER TABLE subject_key ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE subject_key FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY subject_key_firm_isolation ON subject_key
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
    # UPDATE permitted (destruction sets destroyed_at + zeroes key_material).
    # DELETE forbidden — a destroyed row is evidence and must remain.
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON subject_key TO {APP_ROLE};"
    )
    op.execute(
        """
        CREATE TRIGGER subject_key_no_delete
        BEFORE DELETE ON subject_key
        FOR EACH ROW EXECUTE FUNCTION niyam_forbid_mutation();
        """
    )

    # -----------------------------------------------------------------
    # erasure_request — status-transition record
    # -----------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE erasure_request (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE RESTRICT,
            subject_key_id UUID NOT NULL
                REFERENCES subject_key(id) ON DELETE RESTRICT,
            requested_by UUID
                REFERENCES app_user(id) ON DELETE SET NULL,
            requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            status TEXT NOT NULL DEFAULT 'pending',
            executed_at TIMESTAMPTZ,
            refusal_reason TEXT,
            CONSTRAINT erasure_request_status_ok CHECK (
                status IN ('pending', 'executed', 'refused')
            ),
            CONSTRAINT erasure_request_terminal_consistency CHECK (
                (status = 'executed' AND executed_at IS NOT NULL AND refusal_reason IS NULL)
                OR (status = 'refused' AND executed_at IS NULL AND refusal_reason IS NOT NULL)
                OR (status = 'pending' AND executed_at IS NULL AND refusal_reason IS NULL)
            )
        );
        """
    )
    op.execute(
        "CREATE INDEX erasure_request_firm_status "
        "ON erasure_request (firm_id, status, requested_at DESC);"
    )
    op.execute(
        "CREATE INDEX erasure_request_subject "
        "ON erasure_request (subject_key_id);"
    )
    op.execute("ALTER TABLE erasure_request ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE erasure_request FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY erasure_request_firm_isolation ON erasure_request
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
        f"GRANT SELECT, INSERT, UPDATE ON erasure_request TO {APP_ROLE};"
    )
    op.execute(
        """
        CREATE TRIGGER erasure_request_no_delete
        BEFORE DELETE ON erasure_request
        FOR EACH ROW EXECUTE FUNCTION niyam_forbid_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS erasure_request_no_delete "
        "ON erasure_request;"
    )
    op.execute("DROP TABLE IF EXISTS erasure_request CASCADE;")
    op.execute(
        "DROP TRIGGER IF EXISTS subject_key_no_delete "
        "ON subject_key;"
    )
    op.execute("DROP TABLE IF EXISTS subject_key CASCADE;")
