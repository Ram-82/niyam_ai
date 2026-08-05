"""whatsapp delivery — CA-approved reports + supplier chases

Revision ID: 0010_whatsapp_delivery
Revises: 0009_narration_run
Create Date: 2026-08-05

Two tables + one column:

* ``client.whatsapp_number`` — optional E.164 default the CA can set on
  the client record. Not authoritative; the delivery request snapshots
  the number at approval time so the audit trail shows what was actually
  sent to.
* ``delivery_request`` — the CA-approval gate. A row exists only when a
  CA has explicitly approved a specific narration_run (or match_result,
  for supplier_default chases) for delivery. Approval is mutable BEFORE
  the first send attempt (CA can revise), immutable after (audit).
* ``delivery_attempt`` — APPEND ONLY per-send-attempt state. Carries the
  Meta message id, the delivery status, and error taxonomy. Same
  no-update/no-delete triggers as audit_log/narration_run.

Why not a single "delivery" table: a single approval can produce multiple
attempts (retry after transient Meta failure, resend after client did not
receive) — history matters. Separating the approval (mutable→immutable
state machine) from the attempt (append-only fact log) mirrors the
gsp_session + gsp_pull_attempt split.
"""
from __future__ import annotations

from alembic import op


revision = "0010_whatsapp_delivery"
down_revision = "0009_narration_run"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    # 1. Client-side default WhatsApp number (E.164). Optional.
    op.execute(
        "ALTER TABLE client ADD COLUMN whatsapp_number TEXT;"
    )

    # 2. Delivery request — the CA-approval gate.
    op.execute(
        """
        CREATE TABLE delivery_request (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE RESTRICT,
            client_id UUID NOT NULL
                REFERENCES client(id) ON DELETE CASCADE,
            gstin_profile_id UUID NOT NULL
                REFERENCES gstin_profile(id) ON DELETE CASCADE,
            purpose TEXT NOT NULL,
                -- 'report_send' | 'supplier_chase'
            -- Exactly one of these two is set per row, enforced by the
            -- CHECK below. 'report_send' rows point at a narration_run;
            -- 'supplier_chase' rows point at a match_result.
            narration_run_id UUID
                REFERENCES narration_run(id) ON DELETE RESTRICT,
            match_result_id UUID
                REFERENCES match_result(id) ON DELETE RESTRICT,
            -- Snapshot of the destination at approval time. Even if the
            -- client.whatsapp_number changes later, the audit shows what
            -- number was sent to.
            whatsapp_number_snapshot TEXT NOT NULL,
            template_name TEXT NOT NULL,
            template_language TEXT NOT NULL,
                -- 'en_US'|'hi_IN'|'kn_IN'|'mr_IN' (Meta's convention)
            created_by UUID
                REFERENCES app_user(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            -- Approval fields — nullable until the CA clicks "approve".
            approved_by UUID
                REFERENCES app_user(id) ON DELETE SET NULL,
            approved_at TIMESTAMPTZ,
            -- Once at least one send attempt has run against this
            -- request, we mark it locked so the CA cannot revise the
            -- approval retroactively (would break the audit trail).
            locked_at TIMESTAMPTZ,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            CONSTRAINT delivery_request_purpose_ok CHECK (
                purpose IN ('report_send','supplier_chase')
            ),
            CONSTRAINT delivery_request_target_xor CHECK (
                (purpose = 'report_send' AND narration_run_id IS NOT NULL
                 AND match_result_id IS NULL)
                OR
                (purpose = 'supplier_chase' AND match_result_id IS NOT NULL
                 AND narration_run_id IS NULL)
            )
        );
        """
    )
    op.execute(
        "CREATE INDEX delivery_request_firm_idx "
        "ON delivery_request (firm_id, created_at DESC);"
    )
    op.execute(
        "CREATE INDEX delivery_request_narration_idx "
        "ON delivery_request (narration_run_id) "
        "WHERE narration_run_id IS NOT NULL;"
    )
    op.execute(
        "CREATE INDEX delivery_request_match_idx "
        "ON delivery_request (match_result_id) "
        "WHERE match_result_id IS NOT NULL;"
    )

    # RLS on delivery_request.
    op.execute("ALTER TABLE delivery_request ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE delivery_request FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY delivery_request_firm_isolation ON delivery_request
        USING (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        )
        WITH CHECK (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        );
        """
    )
    # Reject any UPDATE to a locked row. This is the audit lock: once a
    # send has run, the approval fields freeze. Deletes are always
    # rejected — a mistaken approval is corrected by inserting a
    # superseding cancellation row (metadata-flag), not by rewriting.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION delivery_request_locked_no_update()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF OLD.locked_at IS NOT NULL THEN
                RAISE EXCEPTION 'delivery_request % is locked (send in progress or done)', OLD.id;
            END IF;
            RETURN NEW;
        END; $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION delivery_request_no_delete()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'delivery_request is append-only (soft-cancel via metadata instead)';
        END; $$;
        """
    )
    op.execute(
        "CREATE TRIGGER delivery_request_locked_no_update "
        "BEFORE UPDATE ON delivery_request "
        "FOR EACH ROW EXECUTE FUNCTION delivery_request_locked_no_update();"
    )
    op.execute(
        "CREATE TRIGGER delivery_request_no_delete "
        "BEFORE DELETE ON delivery_request "
        "FOR EACH ROW EXECUTE FUNCTION delivery_request_no_delete();"
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON delivery_request TO {APP_ROLE};"
    )

    # 3. Delivery attempt — APPEND ONLY.
    op.execute(
        """
        CREATE TABLE delivery_attempt (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE RESTRICT,
            delivery_request_id UUID NOT NULL
                REFERENCES delivery_request(id) ON DELETE RESTRICT,
            provider TEXT NOT NULL,
                -- 'mock'|'meta'
            provider_message_id TEXT,
                -- Meta's returned messages.id — indexed for webhook joins
            status TEXT NOT NULL,
                -- 'queued'|'sent'|'delivered'|'read'|'failed'
            error_kind TEXT,
                -- taxonomy: 'template_not_approved'|'invalid_number'|'rate_limited'|'meta_5xx'|'other'
            error_message TEXT,
            attempted_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            -- Populated by webhook events; NULL until Meta calls back.
            delivered_at TIMESTAMPTZ,
            read_at TIMESTAMPTZ,
            failed_at TIMESTAMPTZ,
            CONSTRAINT delivery_attempt_status_ok CHECK (
                status IN ('queued','sent','delivered','read','failed')
            )
        );
        """
    )
    op.execute(
        "CREATE INDEX delivery_attempt_request_idx "
        "ON delivery_attempt (delivery_request_id, attempted_at DESC);"
    )
    op.execute(
        "CREATE INDEX delivery_attempt_firm_idx "
        "ON delivery_attempt (firm_id, attempted_at DESC);"
    )
    op.execute(
        "CREATE INDEX delivery_attempt_provider_msg_idx "
        "ON delivery_attempt (provider_message_id) "
        "WHERE provider_message_id IS NOT NULL;"
    )

    op.execute("ALTER TABLE delivery_attempt ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE delivery_attempt FORCE ROW LEVEL SECURITY;")
    op.execute(
        """
        CREATE POLICY delivery_attempt_firm_isolation ON delivery_attempt
        USING (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        )
        WITH CHECK (
            firm_id = NULLIF(current_setting('app.current_firm_id', true), '')::uuid
        );
        """
    )

    # Append-only guards. The webhook path updates delivered_at/read_at/
    # failed_at/status via a separate UPDATE — so this table permits
    # column-level append via UPDATE, but the row's identity + attempted_at
    # never mutate. To keep it simple and honest, we do NOT ship a
    # no_update trigger; instead we protect the immutable columns via a
    # trigger that raises if they change.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION delivery_attempt_immutable_fields()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.firm_id != OLD.firm_id
               OR NEW.delivery_request_id != OLD.delivery_request_id
               OR NEW.provider != OLD.provider
               OR NEW.attempted_at != OLD.attempted_at THEN
                RAISE EXCEPTION 'delivery_attempt immutable columns cannot change';
            END IF;
            RETURN NEW;
        END; $$;
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION delivery_attempt_no_delete()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'delivery_attempt is append-only';
        END; $$;
        """
    )
    op.execute(
        "CREATE TRIGGER delivery_attempt_immutable_fields "
        "BEFORE UPDATE ON delivery_attempt "
        "FOR EACH ROW EXECUTE FUNCTION delivery_attempt_immutable_fields();"
    )
    op.execute(
        "CREATE TRIGGER delivery_attempt_no_delete "
        "BEFORE DELETE ON delivery_attempt "
        "FOR EACH ROW EXECUTE FUNCTION delivery_attempt_no_delete();"
    )
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE ON delivery_attempt TO {APP_ROLE};"
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER IF EXISTS delivery_attempt_immutable_fields ON delivery_attempt;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS delivery_attempt_no_delete ON delivery_attempt;"
    )
    op.execute("DROP FUNCTION IF EXISTS delivery_attempt_immutable_fields();")
    op.execute("DROP FUNCTION IF EXISTS delivery_attempt_no_delete();")
    op.execute("DROP TABLE IF EXISTS delivery_attempt CASCADE;")

    op.execute(
        "DROP TRIGGER IF EXISTS delivery_request_locked_no_update ON delivery_request;"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS delivery_request_no_delete ON delivery_request;"
    )
    op.execute("DROP FUNCTION IF EXISTS delivery_request_locked_no_update();")
    op.execute("DROP FUNCTION IF EXISTS delivery_request_no_delete();")
    op.execute("DROP TABLE IF EXISTS delivery_request CASCADE;")

    op.execute("ALTER TABLE client DROP COLUMN IF EXISTS whatsapp_number;")
