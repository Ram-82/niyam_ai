"""Auth orchestration — the functions the API layer calls.

These functions try to keep RLS discipline tight:

* Every write path on behalf of an authenticated user runs inside a
  ``firm_scoped_session`` pinned to that user's firm_id.
* Two paths are allowed to touch the owner engine (RLS-bypass):
    1. Invite lookup during registration — the caller has no session yet.
    2. User lookup during login — the caller has no session yet.
* Both of those lookups are keyed by a secret (invite token hash) or a
  globally-unique field (email) so cross-firm scanning is not a concern.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.auth import lockout, totp as totp_mod
from app.auth.passwords import (
    assert_password_strength,
    hash_password,
    verify_password,
)
from app.db import firm_scoped_session, owner_engine
from app.models.tables import AppUser, UserInvite


# Static bcrypt hash used to burn cycles when the email doesn't exist. This
# equalizes wall-time between the "user found" and "user missing" paths so
# a timing side channel cannot be used for account enumeration.
_DUMMY_HASH = (
    "$2b$12$abcdefghijklmnopqrstuu4TRvGkOR6r9nGrHqjXzQ1AmMBaxfa2"
)


class AccountLockedError(Exception):
    """Too many failed attempts in the current window."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("account temporarily locked")
        self.retry_after = retry_after


class InvalidCredentialsError(Exception):
    """Wrong email/password/TOTP combo."""


class AccountInactiveError(Exception):
    """User row exists but is_active=false."""


class InvalidInviteError(Exception):
    """Invite is missing, expired, or already accepted."""


class WeakPasswordError(Exception):
    """Password does not meet policy. Re-raised from passwords module."""


def hash_invite_token(raw: str) -> str:
    """SHA-256 hex of the raw invite token — stored in ``user_invite.token_hash``.

    Bcrypt would be overkill (invite tokens are 32 random bytes, not
    memorized secrets). Sha-256 gives us a fixed-length hex string, uniform
    across the invite table, and cheap to look up.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_from_invite(invite_token: str, password: str) -> AppUser:
    """Create an ``app_user`` row from a valid invite.

    Flow:
    1. Look up the invite by token_hash via the owner engine (caller has not
       authenticated; RLS would block a cross-firm scan by email).
    2. Validate: not expired, not accepted.
    3. Enforce password policy.
    4. Open a firm-scoped session pinned to the invite's firm_id and do all
       writes there — the RLS ``WITH CHECK`` will validate every INSERT.
    """
    assert_password_strength(password)

    token_hash = hash_invite_token(invite_token)
    now = datetime.now(tz=timezone.utc)

    # Step 1: look up the invite via the owner engine. The token_hash column
    # is globally UNIQUE so at most one row can match.
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, firm_id, email, role, expires_at, accepted_at
                FROM user_invite
                WHERE token_hash = :h
                """
            ),
            {"h": token_hash},
        ).mappings().first()
    if row is None:
        raise InvalidInviteError("invite not found")
    if row["accepted_at"] is not None:
        raise InvalidInviteError("invite already used")
    if row["expires_at"] <= now:
        raise InvalidInviteError("invite expired")

    firm_id = row["firm_id"]
    invite_id = row["id"]
    email = row["email"]
    role = row["role"]
    password_hash = hash_password(password)

    # Step 2: open a firm-scoped session for the writes. RLS is in force.
    with firm_scoped_session(firm_id) as session:
        user = AppUser(
            firm_id=firm_id,
            email=email,
            password_hash=password_hash,
            role=role,
            totp_confirmed=False,
            is_active=True,
        )
        session.add(user)
        session.flush()

        # Mark the invite accepted. This runs through RLS too — the invite's
        # firm_id equals the pinned GUC so the UPDATE is permitted.
        session.execute(
            update(UserInvite)
            .where(UserInvite.id == invite_id)
            .values(accepted_at=now)
        )
        # Expire so callers get a fresh object after commit.
        session.expire_on_commit = False
        # Force load of attributes before session closes.
        _ = (user.id, user.firm_id, user.email, user.role)

    return user


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


def _lookup_user_by_email(email: str) -> Optional[AppUser]:
    """Owner-engine lookup by email. RLS is bypassed intentionally — the
    caller cannot know firm_id until we return one. Email is globally
    UNIQUE (see 0001_initial), so this scans at most one row."""
    session = Session(bind=owner_engine, expire_on_commit=False)
    try:
        stmt = select(AppUser).where(AppUser.email == email)
        return session.execute(stmt).scalar_one_or_none()
    finally:
        session.close()


def authenticate(email: str, password: str) -> AppUser:
    """Return the ``AppUser`` if credentials are valid, else raise.

    Rules:
    * Raise ``AccountLockedError`` immediately if the email is locked out.
    * On wrong email or wrong password, call ``lockout.record_failure`` and
      raise ``InvalidCredentialsError``.
    * On is_active=false, raise ``AccountInactiveError``.
    * On success, clear the lockout counter. Caller is responsible for
      updating ``last_login_at`` inside a firm-scoped session.
    * Timing: even when the email is unknown, we perform a bcrypt verify
      against a static hash so the wall time roughly matches the "user
      exists but password wrong" path. Prevents enumeration.
    """
    if lockout.is_locked(email):
        raise AccountLockedError(retry_after=max(1, lockout.ttl_seconds(email)))

    user = _lookup_user_by_email(email)
    if user is None:
        # Burn bcrypt cycles to equalize timing before failing.
        verify_password(password, _DUMMY_HASH)
        lockout.record_failure(email)
        raise InvalidCredentialsError("invalid credentials")

    if not verify_password(password, user.password_hash):
        lockout.record_failure(email)
        raise InvalidCredentialsError("invalid credentials")

    if not user.is_active:
        raise AccountInactiveError("account is inactive")

    lockout.clear(email)
    return user


def touch_last_login(user_id: uuid.UUID | str, firm_id: uuid.UUID | str) -> None:
    """Update ``app_user.last_login_at`` inside a firm-scoped session."""
    with firm_scoped_session(firm_id) as session:
        session.execute(
            update(AppUser)
            .where(AppUser.id == user_id)
            .values(last_login_at=datetime.now(tz=timezone.utc))
        )


# ---------------------------------------------------------------------------
# TOTP setup / verify
# ---------------------------------------------------------------------------


def begin_totp_setup(user_id: uuid.UUID | str, firm_id: uuid.UUID | str, email: str) -> tuple[str, str]:
    """Return ``(provisioning_uri, secret)``.

    Idempotent-ish: if the user already has a secret but has not confirmed,
    return the SAME secret so they can re-scan the QR. If confirmed, raise.
    """
    with firm_scoped_session(firm_id) as session:
        user = session.get(AppUser, uuid.UUID(str(user_id)))
        if user is None:
            raise InvalidCredentialsError("user not found")
        if user.totp_confirmed:
            raise InvalidCredentialsError("totp already confirmed")
        if not user.totp_secret:
            user.totp_secret = totp_mod.generate_secret()
            session.add(user)
            session.flush()
        secret = user.totp_secret
    uri = totp_mod.provisioning_uri(secret, email)
    return uri, secret


def confirm_totp(user_id: uuid.UUID | str, firm_id: uuid.UUID | str, code: str) -> AppUser:
    """Verify ``code`` against the stored secret and mark confirmed."""
    with firm_scoped_session(firm_id) as session:
        user = session.get(AppUser, uuid.UUID(str(user_id)))
        if user is None or not user.totp_secret:
            raise InvalidCredentialsError("totp not initialized")
        if not totp_mod.verify_totp(user.totp_secret, code):
            raise InvalidCredentialsError("invalid totp")
        user.totp_confirmed = True
        session.add(user)
        session.flush()
        # Materialize attributes so the caller can read them after commit.
        _ = (user.id, user.firm_id, user.email, user.role, user.totp_confirmed)
        return user
