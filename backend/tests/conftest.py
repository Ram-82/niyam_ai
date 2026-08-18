"""Shared fixtures.

Tests need two capabilities:

1. Superuser access to set up baseline data across firms (owner_conn).
2. App-role access, subject to RLS, to prove that isolation actually holds
   (app_conn — wraps a SET ROLE + set_config).

The test DB is expected to be the same Postgres started by
docker-compose (localhost:5432 / niyam / niyam / niyam) with the
initial migration already applied.
"""
from __future__ import annotations

import os
import uuid
from typing import Iterator

# ---------------------------------------------------------------------------
# Env guards — must run BEFORE any `from app.config import settings` (or
# `import app.gsp.crypto`) is triggered by test collection.
#
# Rationale:
#   1. The developer's ``.env`` may set ``GSP_MODE=whitebooks`` (or another
#      live-mode value) for staging probes. Tests should NEVER call a
#      real vendor — force ``GSP_MODE=mock`` so
#      (a) sandbox_mode flags read True as the suite expects, and
#      (b) ``app.gsp.crypto`` uses the dev default key path.
#   2. The dev default key path only kicks in when ``GSP_ENCRYPTION_KEYS``
#      is empty; if the developer set it in ``.env`` (harmless in prod,
#      contradictory in tests) inject the deterministic dev key so
#      encryption is reproducible in the test session.
#
# pydantic-settings priority order is: init args > env vars > .env file >
# defaults. So ``os.environ`` writes here override anything the developer
# put in ``.env``.
os.environ["GSP_MODE"] = "mock"
os.environ["GSP_ENCRYPTION_KEYS"] = (
    "1:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
)

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.config import settings
from app.db import owner_engine


TRUNCATE_ORDER = (
    "delivery_attempt",
    "delivery_request",
    "supplier_contact",
    "filing_run",
    "match_result",
    "reconciliation_run",
    "b2b_entry",
    "gstn_pull",
    "validation_flag",
    "ocr_extraction",
    "invoice",
    "narration_run",
    "narrator_call_log",
    "readiness_snapshot",
    "consent_log",
    "audit_log",
    "import_job",
    "gsp_pull_attempt",
    "gsp_call_log",
    "gsp_session",
    "client_assignment",
    "gstin_profile",
    "user_invite",
    "app_user",
    "client",
    "ca_firm",
    # `rule_pack` is intentionally NOT truncated here — migration 0004 seeds
    # v1.0.0 as the active pack and the validation/reconciliation/scoring
    # engines all depend on that row. Tests that want a custom pack should
    # UPDATE active=FALSE on the seed and INSERT their own row, undoing in
    # teardown; the partial unique index enforces mutual exclusion.
)


@pytest.fixture(scope="session", autouse=True)
def _enable_test_helpers() -> None:
    """Set ``NIYAM_ALLOW_TEST_HELPERS=1`` for the pytest session so
    ``tests/support/lockout_admin.py`` and friends refuse to run outside
    tests. See P2.1 Stage C. This is intentionally session-scoped and
    autouse; individual tests cannot opt out."""
    import os

    os.environ["NIYAM_ALLOW_TEST_HELPERS"] = "1"


@pytest.fixture(scope="session", autouse=True)
def _require_test_db() -> None:
    """Refuse to run tests against a non-test database."""
    url = settings.database_url
    if "niyam" not in url:
        pytest.exit(f"Unsafe test DB target: {url!r}", returncode=2)


@pytest.fixture(scope="session", autouse=True)
def _ensure_schema_at_head(_require_test_db) -> None:
    """Run ``alembic upgrade head`` at session start so a new migration
    landing between test runs doesn't require the developer to remember
    to run it. Idempotent — Alembic no-ops if already at head."""
    import os
    from alembic import command
    from alembic.config import Config

    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _ensure_rule_pack_seed(_ensure_schema_at_head) -> None:
    """Guarantee the v1.0.0 rule pack seed is present + active.

    The migration ``0004_seed_rule_pack`` seeds it, but a fresh test DB or
    a previous ``clean_db`` run against an older ``TRUNCATE_ORDER`` (which
    included ``rule_pack``) may have left the row missing. This session-
    scoped fixture makes tests robust to either — using the same
    ``PAYLOAD`` the migration uses, so there is no drift.
    """
    import json
    from app.rules.default_pack import PAYLOAD, VERSION

    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO rule_pack (version, payload, active, notes) "
                "VALUES (:v, CAST(:p AS JSONB), TRUE, 'ensured by conftest') "
                "ON CONFLICT (version) DO UPDATE "
                "SET payload = EXCLUDED.payload, active = TRUE"
            ),
            {"v": VERSION, "p": json.dumps(PAYLOAD)},
        )


@pytest.fixture(autouse=True)
def clean_db() -> Iterator[None]:
    """Truncate all tenant tables between tests, as the owner (bypasses RLS).

    Re-seeds ``rule_pack`` after every truncate. ``ca_firm`` is truncated
    CASCADE, and migration 0016 added ``rule_pack.firm_id → ca_firm``, so
    the cascade wipes rule_pack even though it is not in TRUNCATE_ORDER.
    Without the re-seed, every test after the first would fail with
    ``NoActiveRulePackError`` (the session-scoped ``_ensure_rule_pack_seed``
    only runs once at session start).
    """
    import json
    from app.rules.default_pack import PAYLOAD, VERSION

    with owner_engine.begin() as conn:
        for t in TRUNCATE_ORDER:
            # Owner has SUPERUSER: can TRUNCATE even append-only tables.
            conn.execute(text(f"TRUNCATE TABLE {t} RESTART IDENTITY CASCADE"))
        conn.execute(
            text(
                "INSERT INTO rule_pack (version, payload, active, notes) "
                "VALUES (:v, CAST(:p AS JSONB), TRUE, 'ensured by conftest') "
                "ON CONFLICT (version) DO UPDATE "
                "SET payload = EXCLUDED.payload, active = TRUE"
            ),
            {"v": VERSION, "p": json.dumps(PAYLOAD)},
        )
    yield


@pytest.fixture
def owner_conn() -> Iterator[Connection]:
    with owner_engine.begin() as conn:
        yield conn


@pytest.fixture(autouse=True)
def _flush_redis() -> Iterator[None]:
    """Flush the auth Redis DB between tests so lockouts / revocations
    from a previous test cannot leak into the next one."""
    try:
        from app.auth.revocation import _redis as _rev_redis
        from app.auth.lockout import _redis as _lock_redis
        from app.gsp.lockout import _redis as _gsp_redis

        _rev_redis.flushdb()
        # In practice all three point at the same DB, but flush all for safety.
        if _lock_redis is not _rev_redis:
            _lock_redis.flushdb()
        if _gsp_redis is not _rev_redis and _gsp_redis is not _lock_redis:
            _gsp_redis.flushdb()
    except Exception:
        # If Redis is not reachable in a given test environment we let the
        # test itself fail with a clearer error later.
        pass
    yield


@pytest.fixture
def fastapi_app():
    """The real FastAPI app, imported lazily so unit tests don't pay the
    startup cost."""
    from app.main import app as _app

    return _app


@pytest.fixture
def test_client(fastapi_app):
    """A synchronous TestClient that bypasses the lifespan startup checks
    if Redis/Postgres are up (which they are in the test docker environment)."""
    from fastapi.testclient import TestClient

    with TestClient(fastapi_app) as client:
        yield client


@pytest.fixture
def bootstrap_firm():
    """Factory: create a firm + first admin user directly via owner engine.

    The very first user in a firm has no invite (chicken-and-egg), so this
    seeds them straight through the owner (RLS-bypass) connection and
    hashes the password + generates and CONFIRMS a TOTP secret so the admin
    can log in immediately with a live code from the returned secret.

    Returns a dict with firm_id, user_id, email, password, totp_secret.
    """
    from app.auth.passwords import hash_password
    from app.auth.totp import generate_secret

    created: list[tuple[str, str]] = []

    def _make(
        firm_name: str = "Test Firm",
        admin_email: str = "admin@example.com",
        admin_password: str = "Correct-Horse-Battery-Staple-42",
    ) -> dict:
        firm_id = uuid.uuid4()
        user_id = uuid.uuid4()
        secret = generate_secret()
        password_hash = hash_password(admin_password)
        with owner_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO ca_firm (id, name) VALUES (:id, :name)"),
                {"id": firm_id, "name": firm_name},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO app_user (
                        id, firm_id, email, password_hash, role,
                        totp_secret, totp_confirmed, is_active
                    ) VALUES (
                        :id, :fid, :email, :ph, 'admin',
                        :ts, TRUE, TRUE
                    )
                    """
                ),
                {
                    "id": user_id,
                    "fid": firm_id,
                    "email": admin_email,
                    "ph": password_hash,
                    "ts": secret,
                },
            )
        created.append((str(firm_id), str(user_id)))
        return {
            "firm_id": firm_id,
            "user_id": user_id,
            "email": admin_email,
            "password": admin_password,
            "totp_secret": secret,
        }

    yield _make


@pytest.fixture
def two_firms() -> tuple[uuid.UUID, uuid.UUID]:
    """Create two firms with one client + one invoice-shaped row each.

    Uses its own owner-scoped transaction and commits before returning, so the
    seed is visible to any subsequent connection (including the RLS-scoped
    app_engine sessions the tests open).
    """
    firm_a = uuid.uuid4()
    firm_b = uuid.uuid4()
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ca_firm (id, name) VALUES (:a, 'Firm A'), (:b, 'Firm B')"
            ),
            {"a": firm_a, "b": firm_b},
        )
        for firm_id, gstin in (
            (firm_a, "29ABCDE1234F1Z5"),
            (firm_b, "27ABCDE5678F1Z8"),
        ):
            client_id = uuid.uuid4()
            gstin_id = uuid.uuid4()
            conn.execute(
                text(
                    "INSERT INTO client (id, firm_id, trade_name) "
                    "VALUES (:cid, :fid, 'Acme')"
                ),
                {"cid": client_id, "fid": firm_id},
            )
            conn.execute(
                text(
                    "INSERT INTO gstin_profile "
                    "(id, firm_id, client_id, gstin, state_code) "
                    "VALUES (:gid, :fid, :cid, :gstin, :state)"
                ),
                {
                    "gid": gstin_id,
                    "fid": firm_id,
                    "cid": client_id,
                    "gstin": gstin,
                    "state": gstin[:2],
                },
            )
            conn.execute(
                text(
                    """
                    INSERT INTO invoice (
                        firm_id, gstin_profile_id, source, direction,
                        invoice_number, invoice_date, taxable_value_paise,
                        total_paise, content_hash
                    ) VALUES (
                        :fid, :gid, 'csv_import', 'purchase',
                        'INV-1', DATE '2026-06-15', 100000,
                        118000, :hash
                    )
                    """
                ),
                {"fid": firm_id, "gid": gstin_id, "hash": f"seed-{firm_id}"},
            )
    return firm_a, firm_b
