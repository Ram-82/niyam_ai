"""narrator cost_paise + per-firm monthly budget + global runtime kill-switch.

Revision ID: 0024_narrator_cost_and_budget
Revises: 0023_subject_key_and_erasure
Create Date: 2026-08-26

Phase 1.4 (P3): production-grade narrator cost control.

Three changes, one migration because they are the same feature:

1. ``narrator_call_log`` grows ``cost_paise BIGINT NULL`` and
   ``pricing_effective_from TIMESTAMPTZ NULL``. NULL means the model
   was unpriced at call time (an unknown model, or the config had no
   entry) — the /narrator cost aggregation surfaces this as
   ``any_unpriced=true`` so the CA never sees a wrong total dressed as
   a right one. The columns are NULLABLE so existing rows written by
   0020 keep working.

2. ``ca_firm`` grows ``monthly_narrator_budget_paise BIGINT NULL``.
   NULL = no limit (current behaviour). The service compares the
   current-calendar-month sum of ``cost_paise`` against this ceiling
   before making the API call. When exhausted, we raise
   ``NarratorBudgetExhausted`` and never silently switch to a cheaper
   model.

3. ``system_settings`` — a single-row table for operator-level flags
   that must be flipped without a deploy. Only ``narrator_globally_disabled``
   ships in this migration. It composes with the env-var
   ``settings.narrator_enabled`` (env is the deploy-time base policy;
   this row is the runtime "off" switch during an incident). No RLS —
   this table has no ``firm_id`` and is operator-scoped.

TODO-VERIFY-PRICING: pricing itself lives in
``backend/app/narrator/pricing.py`` with an effective-from date. This
migration does not encode any USD or paise price.
"""
from __future__ import annotations

from alembic import op


revision = "0024_narrator_cost_and_budget"
down_revision = "0023_subject_key_and_erasure"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    # -----------------------------------------------------------------
    # narrator_call_log.cost_paise + pricing_effective_from
    # -----------------------------------------------------------------
    # NULLABLE on purpose: rows written by the mock adapter (no LLM
    # call, no tokens) and rows for models missing from the pricing
    # config both stay NULL. The aggregation SQL treats NULL as
    # "unpriced" rather than zero.
    op.execute(
        "ALTER TABLE narrator_call_log "
        "ADD COLUMN cost_paise BIGINT;"
    )
    op.execute(
        "ALTER TABLE narrator_call_log "
        "ADD COLUMN pricing_effective_from TIMESTAMPTZ;"
    )
    # Index for the per-month per-firm budget check. Partial index on
    # NON-NULL cost_paise so the budget SUM ignores unpriced rows
    # cheaply.
    op.execute(
        "CREATE INDEX narrator_call_log_firm_month_cost "
        "ON narrator_call_log (firm_id, at) "
        "WHERE cost_paise IS NOT NULL;"
    )

    # -----------------------------------------------------------------
    # ca_firm.monthly_narrator_budget_paise
    # -----------------------------------------------------------------
    # NULL = no limit; matches pre-migration behaviour. Non-negative
    # check so a typo can't invert the meaning.
    op.execute(
        "ALTER TABLE ca_firm "
        "ADD COLUMN monthly_narrator_budget_paise BIGINT;"
    )
    op.execute(
        "ALTER TABLE ca_firm "
        "ADD CONSTRAINT ca_firm_monthly_narrator_budget_nonneg "
        "CHECK (monthly_narrator_budget_paise IS NULL "
        "OR monthly_narrator_budget_paise >= 0);"
    )

    # -----------------------------------------------------------------
    # system_settings — single-row operator flags
    # -----------------------------------------------------------------
    # No firm_id, no RLS. The CHECK on ``id = 1`` plus PRIMARY KEY
    # enforces the single-row invariant so a bug can't leave the app
    # confused between two conflicting rows.
    #
    # ``updated_by`` is deliberately a plain UUID column with NO
    # foreign key to app_user. A FK would make ``TRUNCATE ca_firm
    # CASCADE`` (used by the test suite's clean_db fixture) transitively
    # wipe this table via ca_firm → app_user → system_settings, taking
    # the seeded singleton with it. The audit trail (who flipped the
    # kill switch) lives in audit_log with the app_user id anyway, so
    # a soft reference here is sufficient.
    op.execute(
        """
        CREATE TABLE system_settings (
            id INT PRIMARY KEY DEFAULT 1,
            narrator_globally_disabled BOOLEAN NOT NULL DEFAULT FALSE,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_by UUID,
            CONSTRAINT system_settings_single_row CHECK (id = 1)
        );
        """
    )
    # Seed the single row so app reads never see a missing settings row.
    op.execute("INSERT INTO system_settings (id) VALUES (1);")
    # App can read and update; INSERT/DELETE reserved for migrations.
    op.execute(f"GRANT SELECT, UPDATE ON system_settings TO {APP_ROLE};")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS system_settings CASCADE;")
    op.execute(
        "ALTER TABLE ca_firm "
        "DROP CONSTRAINT IF EXISTS ca_firm_monthly_narrator_budget_nonneg;"
    )
    op.execute(
        "ALTER TABLE ca_firm "
        "DROP COLUMN IF EXISTS monthly_narrator_budget_paise;"
    )
    op.execute(
        "DROP INDEX IF EXISTS narrator_call_log_firm_month_cost;"
    )
    op.execute(
        "ALTER TABLE narrator_call_log "
        "DROP COLUMN IF EXISTS pricing_effective_from;"
    )
    op.execute(
        "ALTER TABLE narrator_call_log "
        "DROP COLUMN IF EXISTS cost_paise;"
    )
