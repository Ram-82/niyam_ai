"""legal_acceptance — firm/user acceptance of versioned Terms + DPA.

Revision ID: 0022_legal_acceptance
Revises: 0021_ca_firm_narrator_toggle
Create Date: 2026-08-19

APPEND-ONLY. Once inserted, an acceptance row is immutable. A new document
version supersedes an older one because the ``content_hash`` differs — the
gate compares against the currently-effective document hash from the
in-code manifest (``app.legal.manifest``), not against the latest row.

Why store the hash denormalised on every acceptance row rather than a FK
to a ``legal_document`` table? So we can prove — years later, after any
manifest change — exactly which bytes each firm accepted. The hash IS the
receipt. A FK-only design would let the document text drift under an
acceptance row.
"""
from __future__ import annotations

from alembic import op


revision = "0022_legal_acceptance"
down_revision = "0021_ca_firm_narrator_toggle"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE legal_acceptance (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE RESTRICT,
            user_id UUID NOT NULL
                REFERENCES app_user(id) ON DELETE RESTRICT,
            -- 'terms' | 'dpa'. Free-form so future doc types (e.g.
            -- 'aup', 'sub_processor_notice') can land without a migration.
            doc_type TEXT NOT NULL,
            -- Version string from the manifest (e.g. '1.0.0'). Free-form.
            doc_version TEXT NOT NULL,
            -- SHA-256, lowercase hex, 64 chars. This is the receipt: the
            -- document bytes at the time of acceptance.
            content_hash TEXT NOT NULL,
            accepted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            -- Client IP as observed by the API. Nullable because a reverse
            -- proxy without X-Forwarded-For or a test client may not
            -- surface one.
            ip_address INET,
            user_agent TEXT,
            CONSTRAINT legal_acceptance_hash_len CHECK (length(content_hash) = 64)
        );
        """
    )
    op.execute(
        "CREATE INDEX legal_acceptance_firm_doc_at "
        "ON legal_acceptance (firm_id, doc_type, accepted_at DESC);"
    )
    op.execute(
        "CREATE INDEX legal_acceptance_firm_current "
        "ON legal_acceptance (firm_id, doc_type, content_hash);"
    )

    op.execute("ALTER TABLE legal_acceptance ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE legal_acceptance FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY legal_acceptance_firm_isolation ON legal_acceptance
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

    # APPEND ONLY — same pattern as audit_log / consent_log / *_call_log.
    op.execute(
        f"GRANT SELECT, INSERT ON legal_acceptance TO {APP_ROLE};"
    )
    op.execute(
        """
        CREATE TRIGGER legal_acceptance_no_update
        BEFORE UPDATE ON legal_acceptance
        FOR EACH ROW EXECUTE FUNCTION niyam_forbid_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER legal_acceptance_no_delete
        BEFORE DELETE ON legal_acceptance
        FOR EACH ROW EXECUTE FUNCTION niyam_forbid_mutation();
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS legal_acceptance_no_delete "
        "ON legal_acceptance;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS legal_acceptance_no_update "
        "ON legal_acceptance;"
    )
    op.execute("DROP TABLE IF EXISTS legal_acceptance CASCADE;")
