"""Runtime settings loaded from env / .env."""
from __future__ import annotations

from pydantic import Field, model_validator
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
    # to a real vendor via the generic X-Api-Key adapter (Master GST
    # shape by default). 'whitebooks' → talk to WhiteBooks (BVM IT) via
    # the WhiteBooks-shaped adapter (custom header set, 3-step async
    # 2B pull). The frontend surfaces a "sandbox mode" tag whenever
    # ``gsp_mode == 'mock'`` and must never remove it in mock mode.
    gsp_mode: str = "mock"
    gsp_base_url: str = "http://gsp-mock:9000"

    # Live-mode credentials + endpoint prefix. Only consulted when
    # gsp_mode='live'; the initial shipped shape matches Master GST's
    # public sandbox (X-Api-Key header, /api/<version>/... paths). Other
    # vendors override via a fork of ``app/gsp/adapter_live.py``.
    #
    # In sandbox mode, register a client_id/client_secret on the vendor's
    # portal and put the values in .env. Never commit them.
    gsp_api_key: str = ""
    gsp_client_id: str = ""
    gsp_client_secret: str = ""
    # Path prefix under gsp_base_url the live vendor uses. Kept as a
    # single setting so a version bump on the vendor side is one env
    # change, not a code change.
    gsp_live_path_prefix: str = "/api/v0.4"

    # WhiteBooks-mode extras. WhiteBooks does not use an API key — it
    # uses a client_id + client_secret + per-request header set
    # (gst_username, state_cd, ip_address, txn). Only consulted when
    # gsp_mode='whitebooks'.
    #
    # gsp_gst_username: the taxpayer's GSTN portal login. In sandbox
    #   this is issued by WhiteBooks (e.g. TN_NT2.152383). In prod it
    #   is the CA's or client's actual portal username.
    # gsp_ip_address: the public IP of this API server. GSTN whitelists
    #   the GSP's IP ranges; in prod this MUST match the IP registered
    #   on the WhiteBooks portal.
    # gsp_developer_email: the developer email registered on the
    #   WhiteBooks portal, used in every ?email= query param.
    gsp_gst_username: str = ""
    gsp_ip_address: str = ""
    gsp_developer_email: str = ""

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
    # 'mock'      → deterministic template renderer, no external calls.
    # 'anthropic' → Claude via the Anthropic SDK; requires anthropic_api_key.
    # 'gemini'    → Google Gemini via google-generativeai SDK; requires
    #               gemini_api_key. Free tier available for pilot volumes.
    narrator_mode: str = "mock"
    # Default: Haiku 4.5. The narrator task (short constrained JSON with
    # frozen facts) is well within Haiku's competence; Opus 4.7 is 15x
    # more expensive for a difference the CA rarely sees. Bump to Sonnet
    # 4.6 or Opus 4.7 per-firm only on quality complaints. See
    # docs/narrator-security.md §Cost.
    narrator_model: str = "claude-haiku-4-5-20251001"
    anthropic_api_key: str = ""
    # Gemini equivalent — only consulted when narrator_mode='gemini'.
    # ``narrator_model`` is repurposed as the Gemini model id in that
    # mode (e.g. 'gemini-2.5-flash'). Free tier: no key needed for
    # certain model+region combos, but the SDK still requires a
    # placeholder; register a project on aistudio.google.com and paste
    # the resulting key here.
    gemini_api_key: str = ""

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

    # OCR (invoice PDF / photo extraction) feature flag + adapter selection.
    # Default OFF — Step 1 ships only the mock adapter and no persistence,
    # so leaving the flag off keeps the /ocr/* endpoints returning 503
    # in every environment that has not explicitly opted in to previewing
    # the extraction shape.
    # 'mock' → deterministic fixture-based extractor, no external calls.
    # Real adapters (pdfminer + tesseract) land in P2.1 Step 3.
    ocr_enabled: bool = False
    ocr_mode: str = "mock"
    # Upload size limit for OCR extractions (bytes). 10 MiB is enough for
    # a multi-page scanned invoice at 300 DPI; larger uploads almost
    # always mean someone attached the wrong file.
    ocr_max_upload_bytes: int = 10 * 1024 * 1024
    # Per-field confidence below which the review UI highlights the
    # field as needing CA attention. Advisory — the validation engine
    # is authoritative for accept-time checks.
    ocr_low_confidence_threshold: float = 0.75

    # Email delivery feature flag + transport selection. Default OFF so no
    # dev/demo run can spam real inboxes. When OFF, the invite endpoint's
    # UI copy-URL fallback is the ONLY way an invite reaches the recipient
    # — which is deliberate and correct until an operator provisions a
    # real transport.
    # 'console' → log the email body via observability; no external call.
    # 'memory'  → in-process transport (tests only, records sends).
    # 'smtp'    → real delivery via SMTP relay (Mailgun, SendGrid, SES SMTP, etc).
    # 'ses'     → future; AWS SES via boto3.
    email_enabled: bool = False
    email_mode: str = "console"
    email_from: str = "no-reply@niyam.ai"
    email_from_name: str = "Niyam AI"
    # Public origin the invite / password-reset links point at. In prod
    # this is the CA-facing dashboard URL (e.g. https://app.niyam.ai).
    email_app_base_url: str = "http://localhost:3000"

    # SMTP relay settings — only required when email_mode='smtp'.
    # Compatible with any SMTP relay: Mailgun, SendGrid, Postmark, AWS SES
    # (SMTP interface), or a bare Postfix/Exim.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    # smtp_use_tls=True  → implicit TLS (SMTP_SSL), typically port 465.
    # smtp_use_starttls=True → STARTTLS upgrade, typically port 587 (default).
    # Set both False for a trusted internal relay on port 25.
    smtp_use_tls: bool = False
    smtp_use_starttls: bool = True

    # SQLAlchemy connection pool tuning.
    # pool_size × WEB_WORKERS = total persistent connections to Postgres.
    # max_overflow × WEB_WORKERS = burst headroom above that.
    # Rule of thumb: keep (pool_size + max_overflow) × workers < pg max_connections − 10.
    db_pool_size: int = 5
    db_pool_max_overflow: int = 10

    # Due-date reminder sweep. Fires when the /scheduler/reminders/sweep
    # cron endpoint runs. Independent of email_enabled — even with the
    # cron wired, the sweep is a no-op until this flips true. Reason:
    # sweeps are heavy (whole-firm fanout) and pre-launch dry-runs would
    # spam every staff account.
    reminders_enabled: bool = False

    @model_validator(mode="after")
    def _check_secrets(self) -> "Settings":
        # JWT secret must be at least 32 bytes. The docker-compose dev default
        # ("dev-only-jwt-secret-change-in-prod", 34 chars) passes; the literal
        # Settings default ("change-me-in-real-env", 22 chars) does not — which
        # is intentional: running uvicorn without any env should fail loudly.
        if len(self.jwt_secret.encode()) < 32:
            raise ValueError(
                "JWT_SECRET must be at least 32 bytes. "
                "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
            )
        # Feature-flag credential checks: only enforce when the mode requires
        # a real external credential (mock modes need no credentials).
        if self.narrator_enabled and self.narrator_mode == "anthropic" and not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY must be set when narrator_enabled=true and narrator_mode='anthropic'"
            )
        if self.narrator_enabled and self.narrator_mode == "gemini" and not self.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY must be set when narrator_enabled=true and narrator_mode='gemini'. "
                "Register at https://aistudio.google.com and paste the key in .env."
            )
        if self.whatsapp_enabled and self.whatsapp_mode == "meta":
            if not self.whatsapp_access_token:
                raise ValueError(
                    "WHATSAPP_ACCESS_TOKEN must be set when whatsapp_enabled=true and whatsapp_mode='meta'"
                )
            if not self.whatsapp_app_secret:
                raise ValueError(
                    "WHATSAPP_APP_SECRET must be set when whatsapp_enabled=true and whatsapp_mode='meta'"
                )
        if self.gsp_mode in ("live", "whitebooks") and "gsp-mock" in self.gsp_base_url:
            raise ValueError(
                f"GSP_BASE_URL still points at the local mock server while "
                f"gsp_mode={self.gsp_mode!r}. Set GSP_BASE_URL to your GSP "
                f"vendor's endpoint (e.g. https://apisandbox.whitebooks.in)."
            )
        if self.gsp_mode == "live" and not self.gsp_api_key:
            raise ValueError(
                "GSP_API_KEY must be set when gsp_mode='live'. Register a "
                "sandbox key on the vendor portal (e.g. sandbox.mastergst.com) "
                "and put it in .env."
            )
        if self.gsp_mode == "whitebooks":
            missing: list[str] = []
            if not self.gsp_client_id:
                missing.append("GSP_CLIENT_ID")
            if not self.gsp_client_secret:
                missing.append("GSP_CLIENT_SECRET")
            if not self.gsp_gst_username:
                missing.append("GSP_GST_USERNAME")
            if not self.gsp_ip_address:
                missing.append("GSP_IP_ADDRESS")
            if not self.gsp_developer_email:
                missing.append("GSP_DEVELOPER_EMAIL")
            if missing:
                raise ValueError(
                    f"gsp_mode='whitebooks' requires: {', '.join(missing)}. "
                    f"Register on developer.whitebooks.in, generate sandbox "
                    f"credentials, and put them in .env."
                )
        if self.email_enabled and self.email_mode == "smtp":
            if not self.smtp_host:
                raise ValueError(
                    "SMTP_HOST must be set when email_enabled=true and email_mode='smtp'. "
                    "Provide the hostname of your SMTP relay (e.g. smtp.mailgun.org)."
                )
        return self


settings = Settings()
