"""Per-firm rule packs — add firm_id to rule_pack

Revision ID: 0016_firm_rule_pack
Revises: 0015_ca_firm_reminders_toggle
Create Date: 2026-08-10

A NULL firm_id means the pack is the global default (applies to every
firm with no firm-specific override). A non-NULL firm_id scopes the
pack to exactly one firm.

Resolution order in get_active_rule_pack():
  1. firm-specific active pack (WHERE firm_id = :fid AND active = TRUE)
  2. global active pack        (WHERE firm_id IS NULL AND active = TRUE)

Index changes:
  * Drop rule_pack_single_active (one global active — too narrow now).
  * Add rule_pack_global_active  (at most one active row with firm_id IS NULL).
  * Add rule_pack_firm_active    (at most one active row per firm_id).
"""
from __future__ import annotations

from alembic import op


revision = "0016_firm_rule_pack"
down_revision = "0015_ca_firm_reminders_toggle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable: existing rows become the global default.
    op.execute(
        "ALTER TABLE rule_pack "
        "ADD COLUMN firm_id UUID REFERENCES ca_firm(id) ON DELETE CASCADE;"
    )
    # Old index allowed exactly one active row globally — too narrow.
    op.execute("DROP INDEX IF EXISTS rule_pack_single_active;")
    # One global active pack.
    op.execute(
        "CREATE UNIQUE INDEX rule_pack_global_active "
        "ON rule_pack ((active)) "
        "WHERE active = TRUE AND firm_id IS NULL;"
    )
    # One active pack per firm.
    op.execute(
        "CREATE UNIQUE INDEX rule_pack_firm_active "
        "ON rule_pack (firm_id) "
        "WHERE active = TRUE AND firm_id IS NOT NULL;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS rule_pack_firm_active;")
    op.execute("DROP INDEX IF EXISTS rule_pack_global_active;")
    op.execute(
        "CREATE UNIQUE INDEX rule_pack_single_active "
        "ON rule_pack ((active)) WHERE active = TRUE;"
    )
    op.execute("ALTER TABLE rule_pack DROP COLUMN IF EXISTS firm_id;")
