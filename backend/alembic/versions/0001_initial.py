"""initial schema: tenancy, invoices, GSTN pulls, engines, rule packs, audit, consent + RLS

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-13

Design notes (also captured in README):

* Multi-tenancy is enforced at the DB layer via Postgres Row-Level Security.
  Every tenant-scoped table carries `firm_id` (denormalized) so RLS policies
  are single-column index scans, not multi-join expressions.

* Migrations run as the DB owner (`niyam`, superuser in dev). The FastAPI
  process connects as `niyam_app`, a NOLOGIN-inheriting role WITHOUT BYPASSRLS,
  so RLS policies always apply. The app sets `SET LOCAL app.current_firm_id`
  inside each request transaction; policies read that GUC.

* Append-only tables (`readiness_snapshot`, `audit_log`, `consent_log`) grant
  only SELECT + INSERT to the app role. UPDATE/DELETE are revoked and, because
  RLS is FORCE'd, superusers are the only path to mutate history (i.e. only
  Alembic / DBA). Event-style semantics live in the app.

* Money is BIGINT paise. No floats anywhere.

* Enums are native Postgres types so the DB itself rejects garbage.

* GSTIN format has a light CHECK for length/character class; the full checksum
  lives in the validation engine (rule R002).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"

# Tables that are strictly append-only (INSERT + SELECT only for the app role).
APPEND_ONLY_TABLES = ("readiness_snapshot", "audit_log", "consent_log")

# Every tenant-scoped table gets the same firm_id-based RLS policy.
TENANT_TABLES = (
    "app_user",
    "client",
    "client_assignment",
    "gstin_profile",
    "invoice",
    "gstn_pull",
    "b2b_entry",
    "validation_flag",
    "match_result",
    "reconciliation_run",
    "readiness_snapshot",
    "audit_log",
    "consent_log",
)


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 0. App role. Idempotent creation.
    # ------------------------------------------------------------------
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') THEN
                CREATE ROLE {APP_ROLE} NOLOGIN;
            END IF;
        END$$;
        """
    )
    # Explicitly ensure this role does NOT bypass RLS.
    op.execute(f"ALTER ROLE {APP_ROLE} NOBYPASSRLS;")

    # ------------------------------------------------------------------
    # 1. Enum types
    # ------------------------------------------------------------------
    op.execute("CREATE TYPE user_role AS ENUM ('admin', 'staff');")
    op.execute("CREATE TYPE gst_scheme AS ENUM ('regular', 'composition');")
    op.execute(
        "CREATE TYPE invoice_source AS ENUM ('csv_import', 'manual', 'api');"
    )
    op.execute("CREATE TYPE invoice_direction AS ENUM ('purchase', 'sale');")
    op.execute(
        "CREATE TYPE invoice_status AS ENUM ('active', 'superseded', 'void');"
    )
    op.execute("CREATE TYPE return_type AS ENUM ('GSTR2B', 'GSTR1', 'GSTR3B');")
    op.execute("CREATE TYPE flag_severity AS ENUM ('error', 'warning');")
    op.execute(
        "CREATE TYPE match_bucket AS ENUM "
        "('matched', 'probable', 'supplier_default', 'missing_entry');"
    )
    op.execute(
        "CREATE TYPE recon_run_status AS ENUM "
        "('pending', 'running', 'completed', 'failed');"
    )
    # Reserved for P2 CDN (credit/debit note) parsing. b2b_entry rows for
    # regular invoices carry NULL. P1 ITC summaries are labeled
    # "before credit/debit note adjustments" until the CDN path is wired.
    op.execute(
        "CREATE TYPE b2b_note_type AS ENUM ('credit_note', 'debit_note');"
    )

    # ------------------------------------------------------------------
    # 2. Core tenancy tables
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")  # gen_random_uuid()
    op.execute("CREATE EXTENSION IF NOT EXISTS citext;")    # case-insensitive email

    op.execute(
        """
        CREATE TABLE ca_firm (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'pilot',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE app_user (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL REFERENCES ca_firm(id) ON DELETE RESTRICT,
            email CITEXT_OR_TEXT_PLACEHOLDER,
            password_hash TEXT NOT NULL,
            role user_role NOT NULL,
            totp_secret TEXT,
            totp_confirmed BOOLEAN NOT NULL DEFAULT FALSE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """.replace(
            "CITEXT_OR_TEXT_PLACEHOLDER",
            # We install citext for case-insensitive email uniqueness.
            "CITEXT NOT NULL",
        )
    )
    op.execute(
        "CREATE UNIQUE INDEX app_user_email_uniq ON app_user (email);"
    )
    op.execute("CREATE INDEX app_user_firm_idx ON app_user (firm_id);")

    op.execute(
        """
        CREATE TABLE client (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL REFERENCES ca_firm(id) ON DELETE RESTRICT,
            trade_name TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'en',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX client_firm_idx ON client (firm_id);")

    op.execute(
        """
        CREATE TABLE client_assignment (
            firm_id UUID NOT NULL REFERENCES ca_firm(id) ON DELETE CASCADE,
            user_id UUID NOT NULL REFERENCES app_user(id) ON DELETE CASCADE,
            client_id UUID NOT NULL REFERENCES client(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (user_id, client_id)
        );
        """
    )
    op.execute(
        "CREATE INDEX client_assignment_firm_idx ON client_assignment (firm_id);"
    )
    op.execute(
        "CREATE INDEX client_assignment_client_idx "
        "ON client_assignment (client_id);"
    )

    op.execute(
        """
        CREATE TABLE gstin_profile (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL REFERENCES ca_firm(id) ON DELETE RESTRICT,
            client_id UUID NOT NULL REFERENCES client(id) ON DELETE CASCADE,
            gstin TEXT NOT NULL,
            state_code TEXT NOT NULL,
            scheme gst_scheme NOT NULL DEFAULT 'regular',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            -- 15-char GSTIN:
            --   [state 2 digits][PAN 5 letters + 4 digits + 1 letter]
            --   [entity code — 1-9 or A-Z, NOT 0]
            --   [default 'Z' but any letter allowed]
            --   [check digit — 0-9 or A-Z]
            -- Structural only; checksum lives in validation rule R002.
            CONSTRAINT gstin_format_chk CHECK (
                gstin ~ '^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z][A-Z][0-9A-Z]$'
            ),
            CONSTRAINT state_code_chk CHECK (state_code ~ '^[0-9]{2}$')
        );
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX gstin_profile_client_gstin_uniq "
        "ON gstin_profile (client_id, gstin);"
    )
    op.execute(
        "CREATE INDEX gstin_profile_firm_idx ON gstin_profile (firm_id);"
    )

    # ------------------------------------------------------------------
    # 3. Invoice + GSTN pull + b2b entry
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE invoice (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL REFERENCES ca_firm(id) ON DELETE RESTRICT,
            gstin_profile_id UUID NOT NULL
                REFERENCES gstin_profile(id) ON DELETE CASCADE,
            source invoice_source NOT NULL,
            direction invoice_direction NOT NULL,
            invoice_number TEXT NOT NULL,
            invoice_date DATE NOT NULL,
            counterparty_gstin TEXT,
            taxable_value_paise BIGINT NOT NULL,
            cgst_paise BIGINT NOT NULL DEFAULT 0,
            sgst_paise BIGINT NOT NULL DEFAULT 0,
            igst_paise BIGINT NOT NULL DEFAULT 0,
            total_paise BIGINT NOT NULL,
            hsn_sac TEXT,
            payload JSONB NOT NULL DEFAULT '{}'::jsonb,
            status invoice_status NOT NULL DEFAULT 'active',
            content_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT invoice_amounts_nonneg CHECK (
                taxable_value_paise >= 0
                AND cgst_paise >= 0
                AND sgst_paise >= 0
                AND igst_paise >= 0
                AND total_paise >= 0
            )
        );
        """
    )
    op.execute("CREATE INDEX invoice_firm_idx ON invoice (firm_id);")
    op.execute(
        "CREATE INDEX invoice_gstin_date_idx "
        "ON invoice (gstin_profile_id, invoice_date);"
    )
    op.execute(
        "CREATE INDEX invoice_counterparty_date_idx "
        "ON invoice (counterparty_gstin, invoice_date);"
    )
    # Content-hash dedup is scoped to the GSTIN profile. Same hash across
    # different GSTINs is allowed (two clients can legitimately hold the same
    # supplier invoice — belt-and-braces).
    op.execute(
        "CREATE UNIQUE INDEX invoice_content_hash_uniq "
        "ON invoice (gstin_profile_id, content_hash);"
    )

    op.execute(
        """
        CREATE TABLE gstn_pull (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL REFERENCES ca_firm(id) ON DELETE RESTRICT,
            gstin_profile_id UUID NOT NULL
                REFERENCES gstin_profile(id) ON DELETE CASCADE,
            return_type return_type NOT NULL,
            period TEXT NOT NULL,  -- 'YYYYMM'
            raw_payload JSONB NOT NULL,
            source TEXT NOT NULL DEFAULT 'json_import',  -- 'json_import' | 'gsp_api'
            pulled_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT gstn_pull_period_chk CHECK (period ~ '^[0-9]{6}$')
        );
        """
    )
    op.execute(
        "CREATE INDEX gstn_pull_gstin_period_idx "
        "ON gstn_pull (gstin_profile_id, return_type, period, pulled_at DESC);"
    )
    op.execute("CREATE INDEX gstn_pull_firm_idx ON gstn_pull (firm_id);")

    op.execute(
        """
        CREATE TABLE b2b_entry (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL REFERENCES ca_firm(id) ON DELETE RESTRICT,
            gstn_pull_id UUID NOT NULL
                REFERENCES gstn_pull(id) ON DELETE CASCADE,
            supplier_gstin TEXT NOT NULL,
            invoice_number TEXT NOT NULL,
            invoice_date DATE NOT NULL,
            taxable_value_paise BIGINT NOT NULL,
            tax_paise_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
            itc_available BOOLEAN NOT NULL DEFAULT TRUE,
            -- NULL for regular invoices. Populated when P2 wires up the
            -- credit/debit note sections of the 2B JSON. Until then, P1 ITC
            -- summaries are labeled "before credit/debit note adjustments."
            note_type b2b_note_type,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX b2b_entry_pull_idx ON b2b_entry (gstn_pull_id);")
    op.execute(
        "CREATE INDEX b2b_entry_supplier_date_idx "
        "ON b2b_entry (supplier_gstin, invoice_date);"
    )
    op.execute("CREATE INDEX b2b_entry_firm_idx ON b2b_entry (firm_id);")

    # ------------------------------------------------------------------
    # 4. Engine outputs: validation flags, reconciliation runs + results
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE validation_flag (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL REFERENCES ca_firm(id) ON DELETE RESTRICT,
            invoice_id UUID NOT NULL REFERENCES invoice(id) ON DELETE CASCADE,
            rule_code TEXT NOT NULL,
            rule_pack_version TEXT NOT NULL,
            severity flag_severity NOT NULL,
            message TEXT NOT NULL,
            resolved BOOLEAN NOT NULL DEFAULT FALSE,
            resolved_by UUID REFERENCES app_user(id) ON DELETE SET NULL,
            resolved_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX validation_flag_invoice_idx "
        "ON validation_flag (invoice_id, resolved);"
    )
    op.execute(
        "CREATE INDEX validation_flag_firm_idx ON validation_flag (firm_id);"
    )

    op.execute(
        """
        CREATE TABLE reconciliation_run (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL REFERENCES ca_firm(id) ON DELETE RESTRICT,
            gstin_profile_id UUID NOT NULL
                REFERENCES gstin_profile(id) ON DELETE CASCADE,
            period TEXT NOT NULL,
            status recon_run_status NOT NULL DEFAULT 'pending',
            rule_pack_version TEXT NOT NULL,
            -- Every run pins the exact 2B snapshot it matched against, in
            -- the same spirit as rule_pack_version. If a re-pull happens
            -- later, historical run summaries stay reproducible.
            gstn_pull_id UUID NOT NULL
                REFERENCES gstn_pull(id) ON DELETE RESTRICT,
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT recon_run_period_chk CHECK (period ~ '^[0-9]{6}$')
        );
        """
    )
    op.execute(
        "CREATE INDEX recon_run_gstin_period_idx "
        "ON reconciliation_run (gstin_profile_id, period, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX recon_run_firm_idx ON reconciliation_run (firm_id);"
    )

    op.execute(
        """
        CREATE TABLE match_result (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL REFERENCES ca_firm(id) ON DELETE RESTRICT,
            run_id UUID NOT NULL
                REFERENCES reconciliation_run(id) ON DELETE CASCADE,
            invoice_id UUID REFERENCES invoice(id) ON DELETE SET NULL,
            b2b_entry_id UUID REFERENCES b2b_entry(id) ON DELETE SET NULL,
            bucket match_bucket NOT NULL,
            confidence NUMERIC(5, 4) NOT NULL DEFAULT 1.0,
            rule_pack_version TEXT NOT NULL,
            confirmed_by UUID REFERENCES app_user(id) ON DELETE SET NULL,
            confirmed_at TIMESTAMPTZ,
            rejected BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT match_has_a_side CHECK (
                invoice_id IS NOT NULL OR b2b_entry_id IS NOT NULL
            ),
            CONSTRAINT match_confidence_range CHECK (
                confidence >= 0 AND confidence <= 1
            )
        );
        """
    )
    op.execute(
        "CREATE INDEX match_result_run_bucket_idx "
        "ON match_result (run_id, bucket);"
    )
    op.execute(
        "CREATE INDEX match_result_invoice_idx ON match_result (invoice_id);"
    )
    op.execute(
        "CREATE INDEX match_result_b2b_idx ON match_result (b2b_entry_id);"
    )
    op.execute(
        "CREATE INDEX match_result_firm_idx ON match_result (firm_id);"
    )

    # ------------------------------------------------------------------
    # 5. Readiness score history (APPEND ONLY)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE readiness_snapshot (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL REFERENCES ca_firm(id) ON DELETE RESTRICT,
            gstin_profile_id UUID NOT NULL
                REFERENCES gstin_profile(id) ON DELETE CASCADE,
            return_type return_type NOT NULL,
            period TEXT NOT NULL,
            score INTEGER NOT NULL,
            blockers JSONB NOT NULL DEFAULT '[]'::jsonb,
            arithmetic JSONB NOT NULL DEFAULT '{}'::jsonb,
            rule_pack_version TEXT NOT NULL,
            computed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT readiness_period_chk CHECK (period ~ '^[0-9]{6}$'),
            CONSTRAINT readiness_score_range CHECK (score BETWEEN 0 AND 100)
        );
        """
    )
    op.execute(
        "CREATE INDEX readiness_snapshot_lookup_idx "
        "ON readiness_snapshot "
        "(gstin_profile_id, return_type, period, computed_at DESC);"
    )
    op.execute(
        "CREATE INDEX readiness_snapshot_firm_idx "
        "ON readiness_snapshot (firm_id);"
    )

    # ------------------------------------------------------------------
    # 6. Rule pack (global, not tenant-scoped)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE rule_pack (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            version TEXT NOT NULL UNIQUE,  -- semver e.g. '1.0.0'
            payload JSONB NOT NULL,
            active BOOLEAN NOT NULL DEFAULT FALSE,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    # At most one active rule pack.
    op.execute(
        "CREATE UNIQUE INDEX rule_pack_single_active "
        "ON rule_pack ((active)) WHERE active = TRUE;"
    )

    # ------------------------------------------------------------------
    # 7. Audit + consent logs (APPEND ONLY)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE audit_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL,
            user_id UUID,
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id UUID,
            diff JSONB NOT NULL DEFAULT '{}'::jsonb,
            at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX audit_log_firm_time_idx ON audit_log (firm_id, at DESC);"
    )
    op.execute(
        "CREATE INDEX audit_log_entity_idx "
        "ON audit_log (entity_type, entity_id);"
    )

    op.execute(
        """
        CREATE TABLE consent_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL REFERENCES ca_firm(id) ON DELETE RESTRICT,
            client_id UUID NOT NULL REFERENCES client(id) ON DELETE CASCADE,
            purpose TEXT NOT NULL,
            granted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at TIMESTAMPTZ,
            granted_by UUID REFERENCES app_user(id) ON DELETE SET NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        """
    )
    op.execute(
        "CREATE INDEX consent_log_client_idx "
        "ON consent_log (client_id, purpose, granted_at DESC);"
    )
    op.execute("CREATE INDEX consent_log_firm_idx ON consent_log (firm_id);")

    # ------------------------------------------------------------------
    # 8. Row-Level Security
    # ------------------------------------------------------------------
    # Enable + FORCE on ca_firm (a user in firm A must not see firm B's row).
    op.execute("ALTER TABLE ca_firm ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE ca_firm FORCE ROW LEVEL SECURITY;")
    # NULLIF(..., '') turns an unset-or-empty GUC into NULL, and firm_id = NULL
    # is NULL (filtered by RLS). This is the safe-fail path if a request forgets
    # to pin the GUC or accidentally pins it to '' — no rows come back and no
    # cast error is raised.
    op.execute(
        """
        CREATE POLICY ca_firm_self ON ca_firm
        USING (
            id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        )
        WITH CHECK (
            id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        );
        """
    )

    # Everything else with firm_id gets the same policy shape.
    for t in TENANT_TABLES:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY;")
        op.execute(
            f"""
            CREATE POLICY {t}_firm_isolation ON {t}
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

    # rule_pack is global; app role only needs read access. RLS off (no
    # tenant column). Explicit REVOKE below prevents writes.
    op.execute("ALTER TABLE rule_pack DISABLE ROW LEVEL SECURITY;")

    # ------------------------------------------------------------------
    # 9. Grants for the app role
    # ------------------------------------------------------------------
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE};")
    op.execute(f"GRANT SELECT ON rule_pack TO {APP_ROLE};")

    # Read/write tables
    read_write = [t for t in TENANT_TABLES if t not in APPEND_ONLY_TABLES]
    read_write.append("ca_firm")
    for t in read_write:
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {t} TO {APP_ROLE};"
        )

    # Append-only tables: SELECT + INSERT only. No UPDATE, no DELETE.
    for t in APPEND_ONLY_TABLES:
        op.execute(f"GRANT SELECT, INSERT ON {t} TO {APP_ROLE};")

    # ------------------------------------------------------------------
    # 10. Trigger belt-and-braces on append-only tables.
    # Even if a future migration accidentally re-GRANTs UPDATE/DELETE,
    # the trigger blocks the mutation.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION niyam_forbid_mutation()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'table % is append-only', TG_TABLE_NAME;
        END$$;
        """
    )
    for t in APPEND_ONLY_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER {t}_no_update
            BEFORE UPDATE ON {t}
            FOR EACH ROW EXECUTE FUNCTION niyam_forbid_mutation();
            """
        )
        op.execute(
            f"""
            CREATE TRIGGER {t}_no_delete
            BEFORE DELETE ON {t}
            FOR EACH ROW EXECUTE FUNCTION niyam_forbid_mutation();
            """
        )


def downgrade() -> None:
    # Drop in reverse dependency order.
    for t in APPEND_ONLY_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS {t}_no_update ON {t};")
        op.execute(f"DROP TRIGGER IF EXISTS {t}_no_delete ON {t};")
    op.execute("DROP FUNCTION IF EXISTS niyam_forbid_mutation();")

    for t in (
        "consent_log",
        "audit_log",
        "rule_pack",
        "readiness_snapshot",
        "match_result",
        "reconciliation_run",
        "validation_flag",
        "b2b_entry",
        "gstn_pull",
        "invoice",
        "gstin_profile",
        "client_assignment",
        "client",
        "app_user",
        "ca_firm",
    ):
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE;")

    for t in (
        "b2b_note_type",
        "recon_run_status",
        "match_bucket",
        "flag_severity",
        "return_type",
        "invoice_status",
        "invoice_direction",
        "invoice_source",
        "gst_scheme",
        "user_role",
    ):
        op.execute(f"DROP TYPE IF EXISTS {t};")

    op.execute(f"DROP ROLE IF EXISTS {APP_ROLE};")
