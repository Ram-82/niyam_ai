"""ca_firm.narrator_enabled — per-firm opt-in for LLM narration

Revision ID: 0021_ca_firm_narrator_toggle
Revises: 0020_narrator_call_log
Create Date: 2026-08-12

Default FALSE (opt-in) — narration costs real Anthropic tokens per firm,
and the CA needs to review the prose quality on their own data before
letting it reach clients. Contrast with ``reminders_enabled`` (default
TRUE, opt-out) which has no per-firm cost.

The global ``NARRATOR_ENABLED`` env var stays as the operator kill
switch: even if a firm has ``narrator_enabled=true``, no calls fire
until the operator flips the global flag on. This gives us two
independent surfaces (ops + firm admin) each of which can shut
narration off, matching the pilot rollout policy.
"""
from __future__ import annotations

from alembic import op


revision = "0021_ca_firm_narrator_toggle"
down_revision = "0020_narrator_call_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE ca_firm ADD COLUMN narrator_enabled BOOLEAN "
        "NOT NULL DEFAULT FALSE;"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE ca_firm DROP COLUMN IF EXISTS narrator_enabled;")
