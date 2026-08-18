"""narrator_call_log (per-call cost + latency + cache-hit meter)

Revision ID: 0020_narrator_call_log
Revises: 0019_ocr_extraction_acceptable
Create Date: 2026-08-12

The narrator hits a paid API (Anthropic) at ~$3–$15 per million tokens.
Without a per-call meter we cannot answer:

* "How much did this firm cost us this month?"
* "Is prompt caching actually reducing our input token spend?"
* "Which model version was in flight when the CA got a bad narration?"

Mirrors ``gsp_call_log`` shape + RLS + APPEND-ONLY guarantees. Token
columns are NULLABLE so mock-adapter rows (no real API call, no
tokens) can still be logged for latency observability.
"""
from __future__ import annotations

from alembic import op


revision = "0020_narrator_call_log"
down_revision = "0019_ocr_extraction_acceptable"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE narrator_call_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE RESTRICT,
            gstin_profile_id UUID
                REFERENCES gstin_profile(id) ON DELETE SET NULL,
            -- 'anthropic' | 'mock'. Free-form so a future 'gemini' adapter
            -- can log here too without a schema change.
            provider TEXT NOT NULL,
            -- 'claude-opus-4-7' etc; captured verbatim from the adapter.
            model TEXT NOT NULL,
            -- Which attempt this row logs. 1 = first call, 2 = retry after
            -- NumberHallucination. Retries share a run.
            attempt INT NOT NULL DEFAULT 1,
            -- 'en' | 'hi' | 'kn' | 'mr'.
            language TEXT NOT NULL,
            succeeded BOOLEAN NOT NULL,
            -- Typed failure kind when !succeeded. Free-form so we can
            -- add new categories without a migration.
            --   'hallucination'    → validator caught a bad number
            --   'adapter_error'    → API / JSON / SDK failure
            --   'facts_unavailable'→ no readiness_snapshot for the triple
            error_kind TEXT,
            -- Token counts extracted from Anthropic response.usage.
            -- NULL on mock adapter (no LLM call was made).
            input_tokens INT,
            output_tokens INT,
            cache_read_input_tokens INT,
            cache_creation_input_tokens INT,
            latency_ms INT NOT NULL,
            at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX narrator_call_log_firm_at "
        "ON narrator_call_log (firm_id, at DESC);"
    )
    op.execute(
        "CREATE INDEX narrator_call_log_meter "
        "ON narrator_call_log (firm_id, provider, at);"
    )

    # RLS — firm isolation, identical pattern to gsp_call_log.
    op.execute("ALTER TABLE narrator_call_log ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE narrator_call_log FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY narrator_call_log_firm_isolation ON narrator_call_log
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

    # APPEND ONLY. Mutation triggers use the shared niyam_forbid_mutation
    # function defined in migration 0001.
    op.execute(f"GRANT SELECT, INSERT ON narrator_call_log TO {APP_ROLE};")
    op.execute(
        """
        CREATE TRIGGER narrator_call_log_no_update
        BEFORE UPDATE ON narrator_call_log
        FOR EACH ROW EXECUTE FUNCTION niyam_forbid_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER narrator_call_log_no_delete
        BEFORE DELETE ON narrator_call_log
        FOR EACH ROW EXECUTE FUNCTION niyam_forbid_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS narrator_call_log_no_delete "
        "ON narrator_call_log;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS narrator_call_log_no_update "
        "ON narrator_call_log;"
    )
    op.execute("DROP TABLE IF EXISTS narrator_call_log CASCADE;")
