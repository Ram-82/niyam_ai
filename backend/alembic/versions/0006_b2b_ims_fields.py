"""b2b_entry.ims_status + b2b_entry.ims_action (IMS-era 2B passthrough)

Revision ID: 0006_b2b_ims_fields
Revises: 0005_match_result_context
Create Date: 2026-07-27

Since November 2024 the GSTR-2B is generated through the Invoice Management
System (IMS): recipients can accept / reject / keep-pending each B2B
invoice, and 2B reflects those actions. The GSTN 2B payload therefore
carries per-invoice IMS status fields (typical shape: ``imsactn`` in
{"A","R","P","NA"} and a matching ``imsts`` string).

P2-stage-1 stores these AS-IS. Zero engine logic reads them yet — that is
called out in the README under "IMS-era 2B semantics" as a
TODO-VERIFY-WITH-CA. Storing them now means every ingest under the new
regime preserves the signal for the day we act on it (e.g. surfacing
"you have 3 pending IMS actions blocking ITC on ₹X" in the workspace).

Both columns are nullable so pre-IMS payloads and non-IMS test fixtures
stay valid. Text (not enums) because the codeset is not yet stable at
the vendor layer.
"""
from __future__ import annotations

from alembic import op


revision = "0006_b2b_ims_fields"
down_revision = "0005_match_result_context"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE b2b_entry ADD COLUMN ims_status TEXT;")
    op.execute("ALTER TABLE b2b_entry ADD COLUMN ims_action TEXT;")


def downgrade() -> None:
    op.execute("ALTER TABLE b2b_entry DROP COLUMN IF EXISTS ims_action;")
    op.execute("ALTER TABLE b2b_entry DROP COLUMN IF EXISTS ims_status;")
