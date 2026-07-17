"""match_result.context JSONB (for near-miss provenance + future annotations)

Revision ID: 0005_match_result_context
Revises: 0004_seed_rule_pack
Create Date: 2026-07-14

The reconciliation engine's Pass 3 discovers "near-misses" — same-supplier
2B entries that scored below the probable threshold but are close enough
that a CA should review before drafting a supplier chase. Persisting these
per-invoice keeps the dashboard's supplier_default detail view stable
between reruns.

``context`` is intentionally generic (JSONB, default '{}') so we can
attach other match-level annotations later (e.g. reviewer notes, override
history) without another migration.
"""
from __future__ import annotations

from alembic import op


revision = "0005_match_result_context"
down_revision = "0004_seed_rule_pack"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE match_result "
        "ADD COLUMN context JSONB NOT NULL DEFAULT '{}'::jsonb;"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE match_result DROP COLUMN IF EXISTS context;")
