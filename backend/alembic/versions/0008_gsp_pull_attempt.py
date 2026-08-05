"""gsp_pull_attempt — durable, queryable state for every GSP-side pull

Revision ID: 0008_gsp_pull_attempt
Revises: 0007_gsp_session_and_call_log
Create Date: 2026-07-27

Why a separate table:

* ``gsp_call_log`` (0007) is per-HTTP-call and APPEND ONLY. Good for
  cost metering, terrible for "was the July pull for GSTIN X done and
  did it succeed?" — that answer needs per-(gstin, period) state that
  can transition running → succeeded / failed / retrying.

* ``gstn_pull`` (0001) is the produce of a successful pull — no row
  exists for a failure, so a UI that reads only ``gstn_pull`` cannot
  distinguish "not yet due" from "tried and silently failed". That is
  the exact silent-failure hole the requirements flag as unforgivable.

``gsp_pull_attempt`` closes both gaps:

* One row per (gstin_profile_id, period, started_at) — history preserved.
* ``status`` transitions: running → succeeded | failed | retry_scheduled.
* On success ``gstn_pull_id`` is populated (FK), so the UI has one link
  to the ingested payload. On failure ``error_kind`` (taxonomy entry) +
  ``error_message`` (safe user-facing string; no vendor secrets) sit
  right on the row.
* ``next_retry_at`` set when the retry policy will try again — a NULL
  here on a failed row means "permanently failed for this window;
  user action required".
"""
from __future__ import annotations

from alembic import op


revision = "0008_gsp_pull_attempt"
down_revision = "0007_gsp_session_and_call_log"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE gsp_pull_attempt (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE RESTRICT,
            gstin_profile_id UUID NOT NULL
                REFERENCES gstin_profile(id) ON DELETE CASCADE,
            period TEXT NOT NULL,           -- YYYYMM
            source TEXT NOT NULL,           -- 'scheduled' | 'manual'
            status TEXT NOT NULL,           -- 'running'|'succeeded'|'failed'|'retry_scheduled'
            attempt_count INT NOT NULL DEFAULT 1,
            error_kind TEXT,                -- GSPErrorKind value; NULL on success
            error_message TEXT,             -- UI-safe short message; no vendor payload
            gstn_pull_id UUID
                REFERENCES gstn_pull(id) ON DELETE SET NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at TIMESTAMPTZ,
            next_retry_at TIMESTAMPTZ,
            CONSTRAINT gsp_pull_attempt_status_ok CHECK (
                status IN ('running','succeeded','failed','retry_scheduled')
            ),
            CONSTRAINT gsp_pull_attempt_source_ok CHECK (
                source IN ('scheduled','manual')
            )
        );
        """
    )
    op.execute(
        "CREATE INDEX gsp_pull_attempt_firm_idx ON gsp_pull_attempt (firm_id);"
    )
    # Latest-attempt lookup per (gstin, period).
    op.execute(
        "CREATE INDEX gsp_pull_attempt_lookup "
        "ON gsp_pull_attempt (gstin_profile_id, period, started_at DESC);"
    )
    # UI "show me failing pulls" — partial index on the loud state.
    op.execute(
        "CREATE INDEX gsp_pull_attempt_failed "
        "ON gsp_pull_attempt (firm_id, finished_at DESC) "
        "WHERE status = 'failed';"
    )

    op.execute("ALTER TABLE gsp_pull_attempt ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE gsp_pull_attempt FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY gsp_pull_attempt_firm_isolation ON gsp_pull_attempt
        USING (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        )
        WITH CHECK (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        );
        """
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON gsp_pull_attempt TO {APP_ROLE};"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS gsp_pull_attempt CASCADE;")
