"""Runtime settings loaded from env / .env."""
from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Owner URL: has BYPASSRLS. Used only by Alembic and test seeding.
    database_url: str = "postgresql+psycopg://niyam:niyam@localhost:5432/niyam"

    # App URL: whatever role the FastAPI process authenticates as. This role
    # MUST be NOBYPASSRLS. In dev it can be the owner URL — the session
    # helper still SET ROLEs down to niyam_app so RLS applies.
    app_database_url: str = Field(
        default="postgresql+psycopg://niyam:niyam@localhost:5432/niyam",
        description="Connection URL for the FastAPI process.",
    )

    # The role the app "runs as" once a connection is established. If the
    # app_database_url already authenticates as this role, SET ROLE is a
    # no-op. If it authenticates as the owner (dev), SET ROLE downgrades so
    # RLS applies.
    app_db_role: str = "niyam_app"

    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-in-real-env"
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 60 * 60 * 24 * 14
    # Short-lived token issued after a valid password on an unconfirmed-TOTP
    # user. Grants access only to /auth/totp/setup + /auth/totp/verify.
    totp_setup_ttl_seconds: int = 600

    display_tz: str = "Asia/Kolkata"

    # Shared filesystem path for uploaded files handed from the API to the
    # worker. Bind-mounted into both containers in docker-compose. In tests
    # we point this at a tmp_path so the two "processes" (test process +
    # sync-executed job) can read from the same place.
    upload_dir: str = "/data/uploads"

    # RQ execution mode. In prod/dev this is True (real Redis worker).
    # Tests flip it False so ``queue.enqueue`` runs the job in-process.
    queue_async: bool = True

    # GSP integration mode. 'mock' → talk to the local MockGSPServer
    # (docker-compose ``gsp-mock`` service on port 9000). 'live' → talk
    # to a real vendor via a real adapter (none shipped yet — Stage 4
    # README documents the swap-in). The frontend surfaces a
    # "sandbox mode" tag whenever ``gsp_mode == 'mock'`` and must never
    # remove it in mock mode.
    gsp_mode: str = "mock"
    gsp_base_url: str = "http://gsp-mock:9000"

    # Machine credential for the scheduler cron trigger. NEVER accept a user
    # JWT here — the sweep runs across firms and should be unavailable to
    # any human account. Cron sets ``X-Scheduler-Token: <this>``. Empty
    # value = scheduler endpoint disabled (dev default before an ops token
    # is provisioned).
    gsp_scheduler_token: str = ""

    # LLM narrator feature flag + adapter selection. Default OFF so the
    # /narrator/preview endpoint returns 503 until an operator explicitly
    # enables it — narration reaches the CA, not the client, but even
    # that surface should stay hidden until the CA has reviewed the
    # prose quality on their firm's own data.
    narrator_enabled: bool = False
    # 'mock' → deterministic template renderer, no external calls.
    # 'anthropic' → Claude via the Anthropic SDK; requires anthropic_api_key.
    narrator_mode: str = "mock"
    narrator_model: str = "claude-opus-4-7"
    anthropic_api_key: str = ""

    # WhatsApp delivery feature flag + Meta Cloud API creds.
    # Default OFF — Meta onboarding is a multi-week bureaucratic pipeline
    # and the CA-approval gate should never light up in a dev / demo
    # environment where a bad send would reach a real phone number.
    whatsapp_enabled: bool = False
    # 'mock' → in-memory transport, deterministic message ids.
    # 'meta' → real Meta Cloud API v20; requires whatsapp_access_token
    #          + whatsapp_phone_number_id + whatsapp_app_secret.
    whatsapp_mode: str = "mock"
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""
    # Meta HMAC secret for POST /whatsapp/webhook signature check.
    whatsapp_app_secret: str = ""
    # One-time challenge/response secret Meta uses on webhook registration
    # (GET /whatsapp/webhook?hub.verify_token=...). Independent of the
    # HMAC app_secret — Meta documents both.
    whatsapp_webhook_verify_token: str = ""
    # Approved template names. These must be pre-approved on the WABA;
    # Meta rejects any send whose template_name is not approved.
    whatsapp_template_report_name: str = "niyam_report_v1"
    whatsapp_template_chase_name: str = "niyam_supplier_chase_v1"

    # Email delivery feature flag + transport selection. Default OFF so no
    # dev/demo run can spam real inboxes. When OFF, the invite endpoint's
    # UI copy-URL fallback is the ONLY way an invite reaches the recipient
    # — which is deliberate and correct until an operator provisions a
    # real transport.
    # 'console' → log the email body via observability; no external call.
    # 'memory'  → in-process transport (tests only, records sends).
    # 'smtp'    → future; will require SMTP host/port/creds.
    # 'ses'     → future; AWS SES via boto3.
    email_enabled: bool = False
    email_mode: str = "console"
    email_from: str = "no-reply@niyam.ai"
    email_from_name: str = "Niyam AI"
    # Public origin the invite / password-reset links point at. In prod
    # this is the CA-facing dashboard URL (e.g. https://app.niyam.ai).
    email_app_base_url: str = "http://localhost:3000"

    # Due-date reminder sweep. Fires when the /scheduler/reminders/sweep
    # cron endpoint runs. Independent of email_enabled — even with the
    # cron wired, the sweep is a no-op until this flips true. Reason:
    # sweeps are heavy (whole-firm fanout) and pre-launch dry-runs would
    # spam every staff account.
    reminders_enabled: bool = False


settings = Settings()
