"""ocr_extraction — persist every OCR extraction attempt for later CA review.

Revision ID: 0018_ocr_extraction
Revises: 0017_firm_admin_whatsapp
Create Date: 2026-08-11

The row captures what the adapter produced (``raw_extraction`` JSONB is
frozen — Step 4's accept flow uses ``edited_extraction`` on a follow-up
migration, not by mutating this column). ``status`` transitions
draft → accepted | rejected land in Step 4; Step 2 only writes rows
with the default status ``draft`` and does NOT grant UPDATE.

The table is mutable — not append-only like ``narration_run`` — because
a real "accept invoice" flow must persist ``invoice_id`` back onto this
row. The immutability we DO want (adapter can't rewrite its own output)
is enforced by a column-level trigger in a later step; Step 2 relies on
the missing UPDATE grant to prevent any mutation whatsoever.

Indexes:
* firm_id + created_at DESC — the CA dashboard list query.
* gstin_profile_id + created_at DESC — per-client review view.
* firm_id + source_content_hash — dedupe check ("we've seen this file
  before") that the frontend can hit before accepting.
"""
from __future__ import annotations

from alembic import op


revision = "0018_ocr_extraction"
down_revision = "0017_firm_admin_whatsapp"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ocr_extraction (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE RESTRICT,
            gstin_profile_id UUID NOT NULL
                REFERENCES gstin_profile(id) ON DELETE CASCADE,
            direction TEXT NOT NULL,
            source_filename TEXT NOT NULL,
            source_content_hash TEXT NOT NULL,   -- sha256 hex
            source_bytes_size INTEGER NOT NULL,
            adapter TEXT NOT NULL,               -- 'mock' | 'pdfminer' | ...
            adapter_version TEXT NOT NULL,
            raw_extraction JSONB NOT NULL,       -- frozen per-field {value, confidence}
            overall_confidence NUMERIC(4,3) NOT NULL,
            warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
            status TEXT NOT NULL DEFAULT 'draft',
            invoice_id UUID
                REFERENCES invoice(id) ON DELETE SET NULL,
            created_by UUID
                REFERENCES app_user(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            decided_at TIMESTAMPTZ,
            decided_by UUID
                REFERENCES app_user(id) ON DELETE SET NULL,
            CONSTRAINT ocr_extraction_status_ok CHECK (
                status IN ('draft','accepted','rejected')
            ),
            CONSTRAINT ocr_extraction_direction_ok CHECK (
                direction IN ('purchase','sale')
            ),
            CONSTRAINT ocr_extraction_confidence_range CHECK (
                overall_confidence BETWEEN 0.000 AND 1.000
            )
        );
        """
    )
    op.execute(
        "CREATE INDEX ocr_extraction_firm_lookup "
        "ON ocr_extraction (firm_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX ocr_extraction_gstin_lookup "
        "ON ocr_extraction (gstin_profile_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX ocr_extraction_hash_lookup "
        "ON ocr_extraction (firm_id, source_content_hash);"
    )

    # RLS.
    op.execute("ALTER TABLE ocr_extraction ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE ocr_extraction FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY ocr_extraction_firm_isolation ON ocr_extraction
        USING (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        )
        WITH CHECK (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        );
        """
    )

    # App role: SELECT + INSERT only. Step 4 (accept/reject) adds UPDATE;
    # withholding it here means the ``status`` column stays effectively
    # immutable until the accept flow is designed + gated on CA approval.
    op.execute(f"GRANT SELECT, INSERT ON ocr_extraction TO {APP_ROLE};")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ocr_extraction CASCADE;")
