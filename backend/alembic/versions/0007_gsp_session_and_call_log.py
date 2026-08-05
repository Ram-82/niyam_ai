"""gsp_session (encrypted GSP tokens) + gsp_call_log (per-call cost meter)

Revision ID: 0007_gsp_session_and_call_log
Revises: 0006_b2b_ims_fields
Create Date: 2026-07-27

Both tables follow the P1 tenancy pattern precisely — denormalized
``firm_id``, RLS ENABLE + FORCE, ``_firm_isolation`` policy, RLS-scoped
grants for ``niyam_app``. See migration 0001_initial for the shape.

Rationale for each:

* ``gsp_session`` holds an encrypted vendor session token per GSTIN
  profile. The plaintext token is NEVER stored — application-layer
  AEAD ciphertext + a small ``key_version`` int lives in the row so
  key rotation is possible without re-consenting every taxpayer.
  Only one live session per gstin_profile — the UNIQUE constraint
  makes "reconnect" a natural UPSERT.

* ``gsp_call_log`` is APPEND ONLY (SELECT + INSERT only, mutation
  triggers). GSPs charge per call — this table is our unit-economics
  audit. Firm-scoped by construction; cross-firm reads blocked by RLS.

The vendor token itself never lands on disk in plaintext. See
``app.gsp.crypto``.
"""
from __future__ import annotations

from alembic import op


revision = "0007_gsp_session_and_call_log"
down_revision = "0006_b2b_ims_fields"
branch_labels = None
depends_on = None


APP_ROLE = "niyam_app"


def upgrade() -> None:
    # ---------------------------------------------------------------
    # gsp_session — encrypted vendor session per GSTIN profile.
    # ---------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE gsp_session (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE RESTRICT,
            gstin_profile_id UUID NOT NULL
                REFERENCES gstin_profile(id) ON DELETE CASCADE,
            -- AEAD ciphertext of the vendor session token. Bytes, never text.
            -- See app/gsp/crypto.py for the envelope format.
            token_ciphertext BYTEA NOT NULL,
            -- Which app-layer encryption key produced token_ciphertext.
            -- Rotation seam: on rotate, decrypt with old key + re-encrypt
            -- with new + bump this int. See README §GSP key rotation.
            key_version INT NOT NULL DEFAULT 1,
            -- Opaque, non-secret vendor state (request ids, refresh markers).
            -- MUST NOT contain the token itself; a CHECK below asserts it's
            -- a JSON object and we don't put secrets here.
            vendor_context JSONB NOT NULL DEFAULT '{}'::jsonb,
            issued_at TIMESTAMPTZ NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            connected_by UUID REFERENCES app_user(id) ON DELETE SET NULL,
            connected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            revoked_at TIMESTAMPTZ,
            -- Populated when the vendor reports CONSENT_REVOKED or
            -- SESSION_EXPIRED mid-lifecycle. Lets the UI show WHY a
            -- connection went cold without another round-trip.
            revoked_reason TEXT,
            CONSTRAINT gsp_session_ctx_is_object
                CHECK (jsonb_typeof(vendor_context) = 'object')
        );
        """
    )
    # One live session per gstin_profile. "Live" == revoked_at IS NULL.
    # A prior revoked row stays for audit; a new live row supersedes.
    op.execute(
        """
        CREATE UNIQUE INDEX gsp_session_live_uniq
        ON gsp_session (gstin_profile_id)
        WHERE revoked_at IS NULL;
        """
    )
    op.execute("CREATE INDEX gsp_session_firm_idx ON gsp_session (firm_id);")
    op.execute(
        "CREATE INDEX gsp_session_expiry_idx "
        "ON gsp_session (expires_at) WHERE revoked_at IS NULL;"
    )

    # ---------------------------------------------------------------
    # gsp_call_log — per-call cost meter. APPEND ONLY.
    # ---------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE gsp_call_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            firm_id UUID NOT NULL
                REFERENCES ca_firm(id) ON DELETE RESTRICT,
            gstin_profile_id UUID
                REFERENCES gstin_profile(id) ON DELETE SET NULL,
            endpoint TEXT NOT NULL,           -- 'consent'|'confirm'|'gstr2b'|'refresh'|'status'
            period TEXT,                       -- YYYYMM for data pulls; NULL otherwise
            succeeded BOOLEAN NOT NULL,
            http_status INT,
            error_kind TEXT,                   -- taxonomy entry when !succeeded
            latency_ms INT NOT NULL,
            at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX gsp_call_log_firm_at ON gsp_call_log (firm_id, at DESC);")
    op.execute(
        "CREATE INDEX gsp_call_log_meter "
        "ON gsp_call_log (firm_id, endpoint, at);"
    )

    # ---------------------------------------------------------------
    # RLS — same pattern as every other tenant table.
    # ---------------------------------------------------------------
    for t in ("gsp_session", "gsp_call_log"):
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

    # ---------------------------------------------------------------
    # Grants.
    # ---------------------------------------------------------------
    # gsp_session is read/write for the app role — we UPSERT and mark revoked.
    op.execute(
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON gsp_session TO {APP_ROLE};"
    )
    # gsp_call_log is APPEND ONLY: SELECT + INSERT only.
    op.execute(f"GRANT SELECT, INSERT ON gsp_call_log TO {APP_ROLE};")

    # ---------------------------------------------------------------
    # Mutation triggers on gsp_call_log — belt & braces.
    # ---------------------------------------------------------------
    op.execute(
        """
        CREATE TRIGGER gsp_call_log_no_update
        BEFORE UPDATE ON gsp_call_log
        FOR EACH ROW EXECUTE FUNCTION niyam_forbid_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER gsp_call_log_no_delete
        BEFORE DELETE ON gsp_call_log
        FOR EACH ROW EXECUTE FUNCTION niyam_forbid_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS gsp_call_log_no_delete ON gsp_call_log;")
    op.execute("DROP TRIGGER IF EXISTS gsp_call_log_no_update ON gsp_call_log;")
    op.execute("DROP TABLE IF EXISTS gsp_call_log CASCADE;")
    op.execute("DROP TABLE IF EXISTS gsp_session CASCADE;")
