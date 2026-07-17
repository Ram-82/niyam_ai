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
from typing import Literal

from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings


ALGORITHM = "HS256"

TokenType = Literal["access", "refresh", "totp_setup"]


class TokenError(Exception):
    """Raised for expired, tampered, or malformed tokens."""


class Claims(BaseModel):
    """The payload we sign inside every JWT.

    ``sub`` is the user id as a string (JWT convention). ``firm_id`` and
    ``role`` are denormalized onto the token so the request handler can pin
    the RLS GUC and enforce role-based access without a DB round trip.
    """

    model_config = ConfigDict(extra="forbid")

    sub: str
    firm_id: str
    role: str
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
    typ: TokenType,
    ttl_seconds: int,
) -> tuple[str, Claims]:
    now = _now_epoch()
    claims = Claims(
        sub=str(user_id),
        firm_id=str(firm_id),
        role=role,
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


def create_access_token(user) -> tuple[str, Claims]:  # noqa: ANN001
    return _build(
        user_id=user.id,
        firm_id=user.firm_id,
        role=user.role,
        typ="access",
        ttl_seconds=settings.jwt_access_ttl_seconds,
    )


def create_refresh_token(user) -> tuple[str, Claims]:  # noqa: ANN001
    return _build(
        user_id=user.id,
        firm_id=user.firm_id,
        role=user.role,
        typ="refresh",
        ttl_seconds=settings.jwt_refresh_ttl_seconds,
    )


def create_totp_setup_token(user) -> tuple[str, Claims]:  # noqa: ANN001
    return _build(
        user_id=user.id,
        firm_id=user.firm_id,
        role=user.role,
        typ="totp_setup",
        ttl_seconds=settings.totp_setup_ttl_seconds,
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
