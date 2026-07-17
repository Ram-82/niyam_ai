"""seed rule_pack v1.0.0 (active)

Revision ID: 0004_seed_rule_pack
Revises: 0003_import_job
Create Date: 2026-07-14

The validation, reconciliation, and scoring engines all pin
``rule_pack_version`` on their outputs. Shipping the app with no active
rule pack would make every engine call fail — so seed one on migration.

Version 1.0.0 payload includes:

* validation.r004_hsn.turnover_slabs — thresholds + severity + min digits
* validation.r006_tax_arithmetic.expected_rates + tolerance_paise
* validation.r007_duplicate.enabled
* reconciliation.date_window_days + amount_tolerance_percent + probable_threshold
* scoring.weights + due_dates by scheme
* notes[] — the TODO-VERIFY-WITH-CA list mirrored from the README

Every field is subject to CA verification before we ship (see the
Domain verification list in the README).
"""
from __future__ import annotations

import json

from alembic import op
from sqlalchemy import text

from app.rules.default_pack import PAYLOAD as _SHARED_PAYLOAD, VERSION as _VERSION


revision = "0004_seed_rule_pack"
down_revision = "0003_import_job"
branch_labels = None
depends_on = None


# The payload lives in ``app.rules.default_pack`` so tests and the
# migration share one source of truth (imported as _SHARED_PAYLOAD above).


def upgrade() -> None:
    # Idempotent: if the seed was previously wiped by a test truncation
    # (older conftest included rule_pack in TRUNCATE_ORDER) and Alembic
    # still thinks 0004 is applied, downgrade+upgrade or a manual
    # re-invoke of upgrade() must not raise on duplicate version. Use
    # ON CONFLICT so a re-run is a no-op.
    op.get_bind().execute(
        text(
            "INSERT INTO rule_pack (version, payload, active, notes) "
            "VALUES (:v, CAST(:p AS JSONB), TRUE, :n) "
            "ON CONFLICT (version) DO NOTHING"
        ),
        {
            "v": _VERSION,
            "p": json.dumps(_SHARED_PAYLOAD),
            "n": "Initial seed",
        },
    )


def downgrade() -> None:
    op.execute(f"DELETE FROM rule_pack WHERE version = '{_VERSION}';")
