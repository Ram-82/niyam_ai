"""/auth endpoints.

Endpoint map:

* POST /auth/register        — accept an invite + password.
* POST /auth/login           — password (+ TOTP if confirmed) -> tokens.
* POST /auth/totp/setup      — issue provisioning URI to unconfirmed users.
* POST /auth/totp/verify     — confirm TOTP + issue real tokens.
* POST /auth/refresh         — rotate refresh + issue new access.
* POST /auth/logout          — revoke both JTIs.
* GET  /auth/me              — the current user's profile.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import (
    get_current_claims,
    get_current_user,
    get_totp_setup_user,
)
from app.auth import audit, lockout, revocation, service
from app.auth.passwords import WeakPasswordError as PWWeakError
from app.auth.tokens import (
    Claims,
    TokenError,
    create_access_token,
    create_refresh_token,
    create_totp_setup_token,
    decode_token,
)
from app.config import settings
from app.db import firm_scoped_session
from app.models.tables import AppUser


router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    invite_token: str = Field(min_length=8)
    password: str


class RegisterResponse(BaseModel):
    user_id: uuid.UUID
    firm_id: uuid.UUID
    next: str = "totp_setup"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: Optional[str] = None


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class TotpSetupResponse(BaseModel):
    totp_setup_token: str
    expires_in: int


class TotpVerifyRequest(BaseModel):
    code: str


class TotpSetupPayload(BaseModel):
    provisioning_uri: str
    secret: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    firm_id: uuid.UUID
    role: str
    totp_confirmed: bool
    last_login_at: Optional[datetime]


# ---------------------------------------------------------------------------
# /register
# ---------------------------------------------------------------------------


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegisterRequest) -> RegisterResponse:
    try:
        user = service.register_from_invite(payload.invite_token, payload.password)
    except PWWeakError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except service.InvalidInviteError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return RegisterResponse(user_id=user.id, firm_id=user.firm_id)


# ---------------------------------------------------------------------------
# /login
# ---------------------------------------------------------------------------


def _issue_token_pair(user: AppUser) -> TokenPair:
    access_token, _ = create_access_token(user)
    refresh_token, _ = create_refresh_token(user)
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_ttl_seconds,
    )


@router.post("/login")
def login(payload: LoginRequest, response: Response):
    email = payload.email

    try:
        user = service.authenticate(email, payload.password)
    except service.AccountLockedError as e:
        response.headers["Retry-After"] = str(e.retry_after)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="account temporarily locked",
            headers={"Retry-After": str(e.retry_after)},
        )
    except service.AccountInactiveError:
        raise HTTPException(status_code=401, detail="account inactive")
    except service.InvalidCredentialsError:
        # Best-effort audit: if the email matches a known user, record the
        # failure through a firm-scoped session so RLS accepts the INSERT.
        _maybe_audit_lockout_transition(email)
        raise HTTPException(status_code=401, detail="invalid credentials")

    # User exists and password is valid.
    if not user.totp_confirmed:
        token, _ = create_totp_setup_token(user)
        return TotpSetupResponse(
            totp_setup_token=token,
            expires_in=settings.totp_setup_ttl_seconds,
        )

    # TOTP required from here on.
    if not payload.totp_code:
        raise HTTPException(status_code=400, detail="totp_required")
    from app.auth.totp import verify_totp

    if not verify_totp(user.totp_secret or "", payload.totp_code):
        lockout.record_failure(email)
        _maybe_audit_lockout_transition(email)
        raise HTTPException(status_code=401, detail="invalid credentials")

    lockout.clear(email)
    service.touch_last_login(user.id, user.firm_id)
    return _issue_token_pair(user)


def _maybe_audit_lockout_transition(email: str) -> None:
    """If this call's failure just crossed the lockout threshold, audit it.

    We look up the user via the owner engine (email is globally unique) so
    we know which firm_id to pin. If the email is unknown we skip the audit
    — we don't want to write firm-less audit rows.
    """
    if not lockout.is_locked(email):
        return
    user = service._lookup_user_by_email(email)  # noqa: SLF001
    if user is None:
        return
    with firm_scoped_session(user.firm_id) as session:
        audit.record(
            session,
            firm_id=user.firm_id,
            actor_user_id=user.id,
            action="auth.lockout",
            entity_type="app_user",
            entity_id=user.id,
            metadata={"reason": "max_failed_attempts"},
        )


# ---------------------------------------------------------------------------
# /totp/setup + /totp/verify
# ---------------------------------------------------------------------------


@router.post("/totp/setup", response_model=TotpSetupPayload)
def totp_setup(user: AppUser = Depends(get_totp_setup_user)) -> TotpSetupPayload:
    try:
        uri, secret = service.begin_totp_setup(user.id, user.firm_id, user.email)
    except service.InvalidCredentialsError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return TotpSetupPayload(provisioning_uri=uri, secret=secret)


@router.post("/totp/verify", response_model=TokenPair)
def totp_verify(
    payload: TotpVerifyRequest,
    claims: Claims = Depends(get_current_claims),
    user: AppUser = Depends(get_totp_setup_user),
) -> TokenPair:
    try:
        user = service.confirm_totp(user.id, user.firm_id, payload.code)
    except service.InvalidCredentialsError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # Revoke the totp_setup token so it cannot be replayed. Remaining TTL:
    remaining = max(0, claims.exp - int(datetime.now(tz=timezone.utc).timestamp()))
    revocation.revoke(claims.jti, remaining)

    service.touch_last_login(user.id, user.firm_id)
    return _issue_token_pair(user)


# ---------------------------------------------------------------------------
# /refresh
# ---------------------------------------------------------------------------


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest) -> TokenPair:
    try:
        claims = decode_token(payload.refresh_token)
    except TokenError:
        raise HTTPException(status_code=401, detail="invalid refresh token")
    if claims.typ != "refresh":
        raise HTTPException(status_code=401, detail="not a refresh token")
    if revocation.is_revoked(claims.jti):
        raise HTTPException(status_code=401, detail="refresh token revoked")

    # Rotation: revoke the old JTI for its remaining lifetime.
    now = int(datetime.now(tz=timezone.utc).timestamp())
    remaining = max(0, claims.exp - now)
    revocation.revoke(claims.jti, remaining)

    # Load the user to build the new tokens.
    from app.auth.service import _lookup_user_by_email  # noqa: F401 — for style

    with firm_scoped_session(claims.firm_id) as session:
        user = session.get(AppUser, uuid.UUID(claims.sub))
        if user is None or not user.is_active or not user.totp_confirmed:
            raise HTTPException(status_code=401, detail="user not eligible")
        _ = (user.id, user.firm_id, user.email, user.role)

    return _issue_token_pair(user)


# ---------------------------------------------------------------------------
# /logout
# ---------------------------------------------------------------------------


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: LogoutRequest,
    claims: Claims = Depends(get_current_claims),
) -> Response:
    # Revoke the access token JTI (if the caller passed one — required by
    # the auth dependency).
    now = int(datetime.now(tz=timezone.utc).timestamp())
    if claims.typ == "access":
        revocation.revoke(claims.jti, max(0, claims.exp - now))

    # Revoke the refresh token too.
    try:
        rclaims = decode_token(payload.refresh_token)
    except TokenError:
        return Response(status_code=204)
    if rclaims.typ == "refresh":
        revocation.revoke(rclaims.jti, max(0, rclaims.exp - now))
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


@router.get("/me", response_model=MeResponse)
def me(user: AppUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        id=user.id,
        email=str(user.email),
        firm_id=user.firm_id,
        role=user.role,
        totp_confirmed=user.totp_confirmed,
        last_login_at=user.last_login_at,
    )
