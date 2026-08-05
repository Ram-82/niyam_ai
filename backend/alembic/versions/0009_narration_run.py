"""narration_run — APPEND ONLY record of every LLM narration generated

Revision ID: 0009_narration_run
Revises: 0008_gsp_pull_attempt
Create Date: 2026-08-05

Why append-only:

* The prose the LLM produced is the *machine's* record. A later CA edit
  belongs on a separate ``narration_edit`` row (P3), so both the original
  and the CA-approved version stay auditable.
* Regeneration against the same facts always inserts a new row — a
  ``narration_run_id`` is the stable handle for "the narration the CA
  reviewed at time T".
* The two BEFORE triggers (``_no_update``, ``_no_delete``) match the
  pattern used for audit_log / consent_log / readiness_snapshot so
  even a widened GRANT cannot mutate history.

``facts`` and ``output`` are both JSONB — capture is verbose but the
volume is small (one row per narration request) and the audit story is
that the CA can always show a client "here is exactly what the machine
said, on what inputs".
"""
from __future__ import annotations

from alembic import op


revision = "0009_narration_run"
down_revision = "0008_gsp_pull_attempt"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE narration_run (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE RESTRICT,
            gstin_profile_id UUID NOT NULL
                REFERENCES gstin_profile(id) ON DELETE CASCADE,
            return_type return_type NOT NULL,     -- ENUM: GSTR2B|GSTR1|GSTR3B
            period TEXT NOT NULL,                 -- YYYYMM
            language TEXT NOT NULL,               -- 'en'|'hi'|'kn'|'mr'
            provider TEXT NOT NULL,               -- 'mock'|'anthropic'|...
            model TEXT NOT NULL,                  -- e.g. 'claude-opus-4-7'
            facts JSONB NOT NULL,                 -- frozen NarrationFacts
            output JSONB NOT NULL,                -- the four prose blocks
            generated_by UUID
                REFERENCES app_user(id) ON DELETE SET NULL,
            generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT narration_run_language_ok CHECK (
                language IN ('en','hi','kn','mr')
            )
        );
        """
    )
    op.execute(
        "CREATE INDEX narration_run_firm_lookup "
        "ON narration_run (firm_id, generated_at DESC);"
    )
    op.execute(
        "CREATE INDEX narration_run_gstin_lookup "
        "ON narration_run (gstin_profile_id, period, generated_at DESC);"
    )

    # RLS.
    op.execute("ALTER TABLE narration_run ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE narration_run FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY narration_run_firm_isolation ON narration_run
        USING (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        )
        WITH CHECK (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        );
        """
    )

    # APPEND ONLY guards — mirror audit_log/consent_log.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION narration_run_no_update()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'table narration_run is append-only';
        END; $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION narration_run_no_delete()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'table narration_run is append-only';
        END; $$;
        """
    )
    op.execute(
        "CREATE TRIGGER narration_run_no_update "
        "BEFORE UPDATE ON narration_run "
        "FOR EACH ROW EXECUTE FUNCTION narration_run_no_update();"
    )
    op.execute(
        "CREATE TRIGGER narration_run_no_delete "
        "BEFORE DELETE ON narration_run "
        "FOR EACH ROW EXECUTE FUNCTION narration_run_no_delete();"
    )

    # App role: SELECT + INSERT only (matches other append-only tables).
    op.execute(f"GRANT SELECT, INSERT ON narration_run TO {APP_ROLE};")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS narration_run_no_update ON narration_run;")
    op.execute("DROP TRIGGER IF EXISTS narration_run_no_delete ON narration_run;")
    op.execute("DROP FUNCTION IF EXISTS narration_run_no_update();")
    op.execute("DROP FUNCTION IF EXISTS narration_run_no_delete();")
    op.execute("DROP TABLE IF EXISTS narration_run CASCADE;")
