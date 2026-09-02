"""ocr_extraction — accept / reject flow enablement

Revision ID: 0019_ocr_extraction_acceptable
Revises: 0018_ocr_extraction
Create Date: 2026-08-11

Widens the ``ocr_extraction`` surface so P2.1 Step 4 can transition
draft → accepted | rejected:

1. ``ALTER TYPE invoice_source ADD VALUE 'ocr'`` — the resulting
   ``Invoice`` row records where it came from. Existing values stay
   (csv_import, manual, api).
2. ``ADD COLUMN edited_extraction JSONB`` — nullable, populated on
   accept when the CA overrode any raw_extraction field before
   accepting. Comparing raw vs edited later gives us an audit trail
   for "the machine said X, the CA changed it to Y".
3. ``GRANT UPDATE ON ocr_extraction TO niyam_app`` — the app role
   needs UPDATE to stamp status, invoice_id, decided_at, decided_by.
   Column-level immutability of the frozen columns (raw_extraction,
   source_content_hash, adapter*, firm_id) is guarded by a BEFORE
   UPDATE trigger below so a bug in application code cannot rewrite
   the machine's original output.
"""
from __future__ import annotations

from alembic import op


revision = "0019_ocr_extraction_acceptable"
down_revision = "0018_ocr_extraction"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    # (1) New enum value. IF NOT EXISTS so a partially-applied upgrade
    # replays cleanly.
    op.execute("ALTER TYPE invoice_source ADD VALUE IF NOT EXISTS 'ocr';")

    # (2) Optional edited-fields column.
    op.execute(
        "ALTER TABLE ocr_extraction "
        "ADD COLUMN IF NOT EXISTS edited_extraction JSONB;"
    )

    # (3) UPDATE grant + frozen-column trigger.
    op.execute(f"GRANT UPDATE ON ocr_extraction TO {APP_ROLE};")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION ocr_extraction_frozen_columns()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.firm_id IS DISTINCT FROM OLD.firm_id THEN
                RAISE EXCEPTION 'ocr_extraction.firm_id is immutable';
            END IF;
            IF NEW.gstin_profile_id IS DISTINCT FROM OLD.gstin_profile_id THEN
                RAISE EXCEPTION 'ocr_extraction.gstin_profile_id is immutable';
            END IF;
            IF NEW.raw_extraction::text IS DISTINCT FROM OLD.raw_extraction::text THEN
                RAISE EXCEPTION 'ocr_extraction.raw_extraction is immutable';
            END IF;
            IF NEW.adapter IS DISTINCT FROM OLD.adapter THEN
                RAISE EXCEPTION 'ocr_extraction.adapter is immutable';
            END IF;
            IF NEW.adapter_version IS DISTINCT FROM OLD.adapter_version THEN
                RAISE EXCEPTION 'ocr_extraction.adapter_version is immutable';
            END IF;
            IF NEW.source_content_hash IS DISTINCT FROM OLD.source_content_hash THEN
                RAISE EXCEPTION 'ocr_extraction.source_content_hash is immutable';
            END IF;
            IF NEW.source_filename IS DISTINCT FROM OLD.source_filename THEN
                RAISE EXCEPTION 'ocr_extraction.source_filename is immutable';
            END IF;
            IF NEW.source_bytes_size IS DISTINCT FROM OLD.source_bytes_size THEN
                RAISE EXCEPTION 'ocr_extraction.source_bytes_size is immutable';
            END IF;
            IF NEW.created_by IS DISTINCT FROM OLD.created_by THEN
                RAISE EXCEPTION 'ocr_extraction.created_by is immutable';
            END IF;
            IF NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'ocr_extraction.created_at is immutable';
            END IF;
            -- Status is a state machine: draft → accepted | rejected.
            -- Once decided the row is locked (any further update raises).
            IF OLD.status <> 'draft' THEN
                RAISE EXCEPTION
                    'ocr_extraction row is locked (status=%); accept/reject '
                    'is a one-shot transition', OLD.status;
            END IF;
            RETURN NEW;
        END; $$;
        """
    )
    op.execute(
        "CREATE TRIGGER ocr_extraction_frozen "
        "BEFORE UPDATE ON ocr_extraction "
        "FOR EACH ROW EXECUTE FUNCTION ocr_extraction_frozen_columns();"
    )


def downgrade() -> None:
    # 'ocr' enum values cannot be removed cleanly in a downgrade — the
    # only way is to rebuild the enum type from scratch, which cascades
    # to every column using it. Leave the enum value in place on downgrade
    # so any Invoice row that referenced it stays readable.
    op.execute("DROP TRIGGER IF EXISTS ocr_extraction_frozen ON ocr_extraction;")
    op.execute("DROP FUNCTION IF EXISTS ocr_extraction_frozen_columns();")
    op.execute(
        "ALTER TABLE ocr_extraction DROP COLUMN IF EXISTS edited_extraction;"
    )
    op.execute(f"REVOKE UPDATE ON ocr_extraction FROM {APP_ROLE};")
