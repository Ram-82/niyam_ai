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

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import (
    get_current_claims,
    get_current_user,
    get_totp_setup_user,
)
from app.auth import audit, lockout, password_reset, rate_limit, revocation, service
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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=8)
    new_password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    firm_id: uuid.UUID
    firm_name: str
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
def register(payload: RegisterRequest, request: Request) -> RegisterResponse:
    _enforce_rate_limit("register_ip", _client_ip(request))
    try:
        user = service.register_from_invite(payload.invite_token, payload.password)
    except PWWeakError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except service.InvalidInviteError as e:
        raise HTTPException(status_code=400, detail=str(e))
    with firm_scoped_session(user.firm_id) as session:
        audit.record(
            session=session,
            firm_id=user.firm_id,
            actor_user_id=user.id,
            action="auth.user_registered",
            entity_type="app_user",
            entity_id=user.id,
            metadata={"role": user.role, "via": "invite"},
        )
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
def login(payload: LoginRequest, request: Request, response: Response):
    email = payload.email
    # Rate limit BEFORE any DB work. IP first (cheap DoS shield) then
    # email — both must pass. Order matters: an attacker cycling through
    # emails from one IP hits the IP limit first and never poisons the
    # per-email counters for real users.
    _enforce_rate_limit("login_ip", _client_ip(request))
    _enforce_rate_limit("login_email", email)

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
    with firm_scoped_session(user.firm_id) as session:
        audit.record(
            session=session,
            firm_id=user.firm_id,
            actor_user_id=user.id,
            action="auth.login",
            entity_type="app_user",
            entity_id=user.id,
            metadata={"totp": True},
        )
    return _issue_token_pair(user)


def _client_ip(request: Request) -> str:
    """Trust the leftmost X-Forwarded-For hop when present.

    Gunicorn runs with ``--forwarded-allow-ips=*`` behind the ingress
    (see docs/deployment.md); if you're deploying behind a CDN, tighten
    that setting or the header is spoofable and the limiter is
    bypassable per-request.
    """
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(policy: str, identifier: str) -> None:
    allowed, retry_after = rate_limit.check(policy, identifier)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate_limited",
            headers={"Retry-After": str(retry_after)},
        )


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
    with firm_scoped_session(user.firm_id) as session:
        audit.record(
            session=session,
            firm_id=user.firm_id,
            actor_user_id=user.id,
            action="auth.totp_confirmed",
            entity_type="app_user",
            entity_id=user.id,
            metadata={},
        )
    return _issue_token_pair(user)


# ---------------------------------------------------------------------------
# /password/forgot + /password/reset
# ---------------------------------------------------------------------------


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    payload: ForgotPasswordRequest, request: Request
) -> Response:
    """Always returns 202 — never leaks whether the email is registered.

    Rate limited by IP + email; both must pass. See rate_limit.POLICIES
    for the caps.
    """
    _enforce_rate_limit("forgot_ip", _client_ip(request))
    _enforce_rate_limit("forgot_email", payload.email)
    password_reset.initiate_password_reset(
        email=payload.email, requester_ip=_client_ip(request)
    )
    return Response(status_code=202)


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(payload: ResetPasswordRequest) -> Response:
    try:
        user = password_reset.complete_password_reset(
            payload.token, payload.new_password
        )
    except PWWeakError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except password_reset.InvalidResetTokenError as e:
        raise HTTPException(status_code=400, detail=str(e))
    # Audit the successful reset. RLS-scoped by the reset's firm_id.
    with firm_scoped_session(user.firm_id) as session:
        audit.record(
            session=session,
            firm_id=user.firm_id,
            actor_user_id=user.id,
            action="auth.password_reset",
            entity_type="app_user",
            entity_id=user.id,
            metadata={},
        )
    return Response(status_code=204)


@router.post("/password/change", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordRequest,
    user: AppUser = Depends(get_current_user),
) -> Response:
    """Self-service password change (authenticated).

    Verifies current password, updates hash, stamps password_changed_at.
    The refresh handler's iat gate invalidates every OTHER outstanding
    session for this user — the caller's current access token still
    works until its 15-min TTL expires.
    """
    try:
        service.change_password(
            user_id=user.id,
            firm_id=user.firm_id,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
    except PWWeakError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except service.InvalidCredentialsError:
        raise HTTPException(status_code=401, detail="invalid current password")

    with firm_scoped_session(user.firm_id) as session:
        audit.record(
            session=session,
            firm_id=user.firm_id,
            actor_user_id=user.id,
            action="auth.password_changed",
            entity_type="app_user",
            entity_id=user.id,
            metadata={},
        )
    return Response(status_code=204)


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
        # A password change since the token was issued invalidates every
        # outstanding refresh token for this user. iat is unix seconds.
        pw_changed = int(user.password_changed_at.timestamp())
        if claims.iat < pw_changed:
            raise HTTPException(status_code=401, detail="password changed; sign in again")
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
    # firm_name is added for the dashboard app-shell — a one-row
    # lookup keyed by the user's own firm_id, RLS-scoped via the
    # dependency's scoped session.
    from sqlalchemy import text
    from app.db import firm_scoped_session
    with firm_scoped_session(user.firm_id) as session:
        firm_name = session.execute(
            text("SELECT name FROM ca_firm WHERE id = :id"),
            {"id": str(user.firm_id)},
        ).scalar() or ""
    return MeResponse(
        id=user.id,
        email=str(user.email),
        firm_id=user.firm_id,
        firm_name=firm_name,
        role=user.role,
        totp_confirmed=user.totp_confirmed,
        last_login_at=user.last_login_at,
    )
