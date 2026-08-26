"""JWT encode/decode + Claims model.

Three token types share one signing key and one decode entrypoint:

* ``access`` — 15 min, stateless. Carries firm_id + role so RLS and
  authorization can happen without a DB lookup on every request.
* ``refresh`` — 14 days, revocation-checked. Rotated on every use (old JTI
  goes into Redis).
* ``totp_setup`` — 10 min, revocation-checked. Issued after a valid
  password on a user with ``totp_confirmed=false``. Grants access only to
  /auth/totp/setup + /auth/totp/verify.

All tokens carry a fresh UUID4 JTI so revocation is well-defined.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings


ALGORITHM = "HS256"

TokenType = Literal["access", "refresh", "totp_setup"]


class TokenError(Exception):
    """Raised for expired, tampered, or malformed tokens."""


class MembershipClaim(BaseModel):
    """One (firm_id, role) tuple in the token's membership list.

    Populated at token mint time from ``user_firm_membership`` (Phase 2).
    The membership list is a HINT only — every request re-validates that
    the active ``firm_id`` is still a live membership row via a DB
    lookup in ``get_current_user``. Never trust the claim alone
    (P3_BUILD_PROMPT §4).
    """

    model_config = ConfigDict(extra="forbid")

    firm_id: str
    role: str


class Claims(BaseModel):
    """The payload we sign inside every JWT.

    ``sub`` is the user id as a string (JWT convention). ``firm_id`` is
    the ACTIVE firm for this token (renaming to ``active_firm_id``
    would ripple through every handler; the semantics of ``firm_id``
    in a Phase-2+ token is "the firm this token was minted for").
    ``role`` is the role in that active firm. ``memberships`` is the
    full (firm, role) list a firm-switcher would render — but is a
    hint, not authoritative.
    """

    model_config = ConfigDict(extra="forbid")

    sub: str
    firm_id: str
    role: str
    memberships: list[MembershipClaim] = Field(default_factory=list)
    typ: TokenType
    jti: str
    iat: int
    exp: int


def _now_epoch() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp())


def _build(
    *,
    user_id: uuid.UUID | str,
    firm_id: uuid.UUID | str,
    role: str,
    memberships: list[MembershipClaim],
    typ: TokenType,
    ttl_seconds: int,
) -> tuple[str, Claims]:
    now = _now_epoch()
    claims = Claims(
        sub=str(user_id),
        firm_id=str(firm_id),
        role=role,
        memberships=memberships,
        typ=typ,
        jti=str(uuid.uuid4()),
        iat=now,
        exp=now + ttl_seconds,
    )
    token = jwt.encode(
        claims.model_dump(),
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )
    return token, claims


def _memberships_for(user) -> list[MembershipClaim]:  # noqa: ANN001
    """Populate the membership list for a token from user_firm_membership.

    Uses ``owner_session`` (bypasses RLS) because a user's memberships
    span firms by definition — an RLS-scoped query would only see
    memberships in ONE firm. Falls back to a single-firm shim built
    from ``user.firm_id`` + ``user.role`` if the user has no
    ``user_firm_membership`` rows yet (defence during rollout).
    """
    from app.db import owner_session
    from sqlalchemy import text

    with owner_session() as db:
        rows = db.execute(
            text(
                "SELECT firm_id::text, role::text "
                "FROM user_firm_membership "
                "WHERE user_id = :uid AND status = 'active' "
                "ORDER BY firm_id"
            ),
            {"uid": str(user.id)},
        ).all()
    if rows:
        return [MembershipClaim(firm_id=r[0], role=r[1]) for r in rows]
    # Backfill guard — if the migration hasn't run yet or a user was
    # inserted between migration and this call, mint a token with the
    # 1:1 shim so login is never broken by a missing membership row.
    return [MembershipClaim(firm_id=str(user.firm_id), role=user.role)]


def create_access_token(user) -> tuple[str, Claims]:  # noqa: ANN001
    return _build(
        user_id=user.id,
        firm_id=user.firm_id,
        role=user.role,
        memberships=_memberships_for(user),
        typ="access",
        ttl_seconds=settings.jwt_access_ttl_seconds,
    )


def create_refresh_token(user) -> tuple[str, Claims]:  # noqa: ANN001
    return _build(
        user_id=user.id,
        firm_id=user.firm_id,
        role=user.role,
        memberships=_memberships_for(user),
        typ="refresh",
        ttl_seconds=settings.jwt_refresh_ttl_seconds,
    )


def create_totp_setup_token(user) -> tuple[str, Claims]:  # noqa: ANN001
    # totp_setup runs before login is fully complete; the caller
    # already knows the target firm. Skip the DB query and use the
    # 1:1 shim — the token grants access only to the totp verify path.
    return _build(
        user_id=user.id,
        firm_id=user.firm_id,
        role=user.role,
        memberships=[MembershipClaim(firm_id=str(user.firm_id), role=user.role)],
        typ="totp_setup",
        ttl_seconds=settings.totp_setup_ttl_seconds,
    )


def create_access_token_for_firm(
    user,  # noqa: ANN001
    active_firm_id: uuid.UUID | str,
    role_in_active: str,
) -> tuple[str, Claims]:
    """Mint an access token whose active firm is ``active_firm_id``.

    Used by the firm-switch endpoint (P2-d). The caller has already
    validated that ``active_firm_id`` is in the user's memberships;
    we still pass through the full membership list so the token
    contains the switcher's context.
    """
    return _build(
        user_id=user.id,
        firm_id=active_firm_id,
        role=role_in_active,
        memberships=_memberships_for(user),
        typ="access",
        ttl_seconds=settings.jwt_access_ttl_seconds,
    )


def create_refresh_token_for_firm(
    user,  # noqa: ANN001
    active_firm_id: uuid.UUID | str,
    role_in_active: str,
) -> tuple[str, Claims]:
    return _build(
        user_id=user.id,
        firm_id=active_firm_id,
        role=role_in_active,
        memberships=_memberships_for(user),
        typ="refresh",
        ttl_seconds=settings.jwt_refresh_ttl_seconds,
    )


def decode_token(token: str) -> Claims:
    """Decode + validate signature and expiry. Raise TokenError on any failure."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[ALGORITHM],
        )
    except JWTError as e:
        raise TokenError(str(e)) from e
    try:
        return Claims.model_validate(payload)
    except Exception as e:  # pydantic ValidationError etc.
        raise TokenError(f"malformed claims: {e}") from e
