"""Database engines, session factories, and the firm-scoped session helper.

Two engines exist deliberately:

* ``app_engine`` — used by API code. Every checked-out connection is set to
  ``niyam_app`` via ``SET ROLE`` so RLS applies even when the URL points at
  the owner in dev. Every request opens a transaction and pins
  ``app.current_firm_id`` via ``SELECT set_config(..., true)``.

* ``owner_engine`` — used only by Alembic (via alembic.ini) and test seeding.
  It authenticates as the owner and does NOT SET ROLE, so it can bypass RLS
  to create baseline fixtures across firms.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from uuid import UUID

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def _make_app_engine() -> Engine:
    engine = create_engine(
        settings.app_database_url,
        future=True,
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def _set_role(dbapi_conn, _connection_record):  # noqa: ANN001
        # SET ROLE must survive ROLLBACKs on the pooled connection. psycopg3
        # defaults to autocommit=False, so an unwrapped SET ROLE lives inside
        # an implicit transaction — if the app later rolls back a transaction
        # on that connection, PostgreSQL reverts the SET ROLE and subsequent
        # queries silently run as the owner (BYPASSRLS). Flip autocommit while
        # we set the role so it becomes a plain session-level setting.
        prev_autocommit = dbapi_conn.autocommit
        try:
            dbapi_conn.autocommit = True
            with dbapi_conn.cursor() as cur:
                cur.execute(f'SET ROLE "{settings.app_db_role}"')
        finally:
            dbapi_conn.autocommit = prev_autocommit

    return engine


def _make_owner_engine() -> Engine:
    return create_engine(
        settings.database_url,
        future=True,
        pool_pre_ping=True,
    )


app_engine: Engine = _make_app_engine()
owner_engine: Engine = _make_owner_engine()

AppSessionLocal = sessionmaker(bind=app_engine, expire_on_commit=False, future=True)
OwnerSessionLocal = sessionmaker(
    bind=owner_engine, expire_on_commit=False, future=True
)


@contextmanager
def firm_scoped_session(firm_id: UUID | str) -> Iterator[Session]:
    """Yield a session where every query is RLS-scoped to ``firm_id``.

    Uses ``set_config(..., is_local=true)`` so the GUC is transaction-scoped —
    a stray commit or pool return can never leak scope to the next request.
    """
    session = AppSessionLocal()
    try:
        session.begin()
        session.execute(
            text("SELECT set_config('app.current_firm_id', :firm_id, true)"),
            {"firm_id": str(firm_id)},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@contextmanager
def owner_session() -> Iterator[Session]:
    """Bypass-RLS session for migrations, seeding, and tests only."""
    session = OwnerSessionLocal()
    try:
        session.begin()
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
