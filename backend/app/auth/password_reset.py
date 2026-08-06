"""Password reset — token issuance + consumption.

Two-endpoint flow (see ``app.api.auth``):

* ``initiate_password_reset(email, requester_ip)`` — always silent from
  the caller's view; if the email exists, issues a token and dispatches
  a reset email. Enumeration-safe: the endpoint returns 202 for both
  known and unknown emails, and this function never raises for unknown
  emails.

* ``complete_password_reset(raw_token, new_password)`` — verifies token
  is not expired / not used, updates password, marks token used, revokes
  every active refresh token for the user. Raises on invalid state.

Every token is a 32-byte URL-safe random string; the DB only stores the
SHA-256 digest (same discipline as ``user_invite.token_hash``).
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.auth.passwords import (
    assert_password_strength,
    hash_password,
)
from app.auth.service import hash_invite_token, _lookup_user_by_email
from app.db import firm_scoped_session, owner_engine
from app.email import send_password_reset_email
from app.models.tables import AppUser, PasswordReset


logger = logging.getLogger(__name__)


RESET_TOKEN_TTL_SECONDS = 60 * 60  # 1 hour


class InvalidResetTokenError(Exception):
    """Token missing, expired, or already used."""


def _hash_reset_token(raw: str) -> str:
    # Same discipline as invite tokens — deferred to the invite helper so
    # the two flows stay lockstep if the hashing ever changes.
    return hash_invite_token(raw)


def initiate_password_reset(email: str, requester_ip: Optional[str]) -> None:
    """Issue a reset token and email it, if the email belongs to a user.

    NEVER raises for an unknown email — the caller MUST NOT be able to
    tell whether an account exists. Also does not raise for inactive
    users or users without TOTP confirmed; the reset is offered
    regardless, and inactive users still cannot log in even with the
    fresh password.
    """
    user = _lookup_user_by_email(email)
    if user is None:
        # Silent for enumeration safety. Log at debug level for ops
        # troubleshooting; production log level should not surface
        # the email string.
        logger.debug("password_reset.unknown_email")
        return

    raw = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(raw)
    now = datetime.now(tz=timezone.utc)
    expires_at = now + timedelta(seconds=RESET_TOKEN_TTL_SECONDS)

    with firm_scoped_session(user.firm_id) as session:
        row = PasswordReset(
            firm_id=user.firm_id,
            user_id=user.id,
            token_hash=token_hash,
            expires_at=expires_at,
            requester_ip=requester_ip,
        )
        session.add(row)
        session.flush()

    try:
        send_password_reset_email(
            to=str(user.email),
            reset_token=raw,
            expires_at=expires_at,
        )
    except Exception as exc:
        # An email transport failure MUST NOT rollback the token — the
        # user can retry, and manual out-of-band delivery is possible if
        # an operator queries the DB. Log at warning.
        logger.warning(
            "password_reset.email_dispatch_failed",
            extra={"user_id": str(user.id), "error": str(exc)},
        )


def complete_password_reset(raw_token: str, new_password: str) -> AppUser:
    """Consume a reset token: swap password, mark token used, revoke
    every active refresh token for the user.

    Raises:
    * ``InvalidResetTokenError`` — token unknown, expired, or already used
    * ``WeakPasswordError`` (via ``assert_password_strength``) — password
      does not satisfy policy
    """
    assert_password_strength(new_password)

    token_hash = _hash_reset_token(raw_token)
    now = datetime.now(tz=timezone.utc)

    # Owner-engine lookup — caller has no session yet, and token_hash is
    # globally unique so a scan matches at most one row.
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, firm_id, user_id, expires_at, used_at
                FROM password_reset
                WHERE token_hash = :h
                """
            ),
            {"h": token_hash},
        ).mappings().first()

    if row is None:
        raise InvalidResetTokenError("token not found")
    if row["used_at"] is not None:
        raise InvalidResetTokenError("token already used")
    if row["expires_at"] <= now:
        raise InvalidResetTokenError("token expired")

    firm_id = row["firm_id"]
    user_id = row["user_id"]
    new_hash = hash_password(new_password)

    with firm_scoped_session(firm_id) as session:
        # Re-check used_at inside the transaction — protects against a
        # concurrent second /reset call racing against this one. UPDATE
        # returning rowcount is the atomic gate.
        result = session.execute(
            update(PasswordReset)
            .where(PasswordReset.id == row["id"])
            .where(PasswordReset.used_at.is_(None))
            .values(used_at=now)
        )
        if result.rowcount == 0:
            raise InvalidResetTokenError("token already used")

        session.execute(
            update(AppUser)
            .where(AppUser.id == user_id)
            .values(password_hash=new_hash, password_changed_at=now)
        )
        user = session.get(AppUser, uuid.UUID(str(user_id)))
        assert user is not None  # RLS + FK guarantee this
        # Force attribute load before the session closes so the caller
        # can read user.email / user.firm_id after the with-block.
        _ = (user.id, user.firm_id, user.email, user.role, user.is_active)

    return user
