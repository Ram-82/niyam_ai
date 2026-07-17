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


settings = Settings()
