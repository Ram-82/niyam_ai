"""FastAPI dependencies for auth + RLS-scoped sessions.

The key rule: any request handler that touches the database receives an
already-scoped Session via ``get_firm_scoped_session`` (or a helper built on
top of it). That session is inside an open transaction with
``app.current_firm_id`` pinned to the caller's firm — RLS applies to every
statement it issues.
"""
from __future__ import annotations

import uuid
from typing import Iterator, Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import revocation
from app.auth.tokens import Claims, TokenError, decode_token
from app.config import Settings, settings
from app.db import AppSessionLocal
from app.models.tables import AppUser


def get_settings() -> Settings:
    return settings


def get_bearer_token(
    authorization: Optional[str] = Header(default=None),
) -> str:
    """Parse ``Authorization: Bearer <token>``. 401 on any deviation."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing authorization header",
        )
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid authorization header",
        )
    return parts[1]


def get_current_claims(token: str = Depends(get_bearer_token)) -> Claims:
    """Decode + verify signature/expiry + check revocation for stateful types.

    Access tokens are stateless (no revocation check on the hot path — /logout
    can still revoke them, but the check is only worth doing for tokens that
    can be re-presented, which access tokens rarely are once they expire).
    Refresh and totp_setup tokens ARE re-presented and MUST be checked.
    """
    try:
        claims = decode_token(token)
    except TokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
        )
    if claims.typ in ("refresh", "totp_setup", "access") and revocation.is_revoked(
        claims.jti
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token has been revoked",
        )
    return claims


def _open_scoped_session(firm_id: str) -> Iterator[Session]:
    """Yield a session with RLS pinned to ``firm_id``. Commits on success."""
    session = AppSessionLocal()
    try:
        session.begin()
        session.execute(
            text("SELECT set_config('app.current_firm_id', :firm_id, true)"),
            {"firm_id": firm_id},
        )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_firm_scoped_session(
    claims: Claims = Depends(get_current_claims),
) -> Iterator[Session]:
    """A firm-scoped Session usable by any authenticated caller.

    Works for both access and totp_setup tokens — pinning by firm_id is safe
    for either because the totp_setup token is bound to a real user row.
    """
    yield from _open_scoped_session(claims.firm_id)


def get_current_user(
    claims: Claims = Depends(get_current_claims),
) -> AppUser:
    """Load the caller's ``AppUser`` in a firm-scoped read.

    Requires ``typ='access'``. Rejects inactive users. Rejects users whose
    TOTP has not been confirmed — an access token should never have been
    issued to them, but we defense-in-depth check here in case.
    """
    if claims.typ != "access":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access token required",
        )
    # Phase 2: the user's identity check runs on owner_session (RLS
    # bypass) because app_user carries a legacy 1:1 firm_id that no
    # longer authoritatively describes tenancy — a partner in firm A
    # and firm B still has app_user.firm_id = A. A firm-scoped
    # AppUser lookup pinned to B would return no row and give a false
    # 401 for a legit membership. Tenancy IS enforced — by the
    # user_firm_membership check below, run in the same session.
    from app.db import owner_session
    from sqlalchemy import text

    with owner_session() as session:
        user = session.get(AppUser, uuid.UUID(claims.sub))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="user not found",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="account inactive",
            )
        if not user.totp_confirmed:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="totp not confirmed",
            )
        # Defence-in-depth: the JWT's active firm_id must map to a
        # LIVE user_firm_membership row. Never trust the claim alone
        # — a forged token that decodes cleanly still fails here
        # because there is no membership row backing it. The lookup
        # is intentionally narrow (user_id + firm_id + status='active')
        # so a suspended or missing membership refuses the request.
        row = session.execute(
            text(
                "SELECT role::text FROM user_firm_membership "
                "WHERE user_id = :uid "
                "  AND firm_id = :fid "
                "  AND status = 'active'"
            ),
            {"uid": str(user.id), "fid": claims.firm_id},
        ).first()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="not a member of the active firm",
            )
        # Override the loaded user's legacy fields so downstream
        # handlers see the ACTIVE firm and role, not the home firm.
        # This is what makes handlers Phase-2-aware without needing
        # a signature change on every one.
        user.firm_id = uuid.UUID(claims.firm_id)
        user.role = row[0]
        # Force load of scalar attrs before session closes.
        _ = (
            user.id,
            user.firm_id,
            user.email,
            user.role,
            user.totp_confirmed,
            user.is_active,
            user.last_login_at,
        )
        return user


def get_totp_setup_user(
    claims: Claims = Depends(get_current_claims),
) -> AppUser:
    """Like get_current_user but for the pre-TOTP flow. typ must be
    ``totp_setup``. totp_confirmed=false is expected."""
    if claims.typ != "totp_setup":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="totp_setup token required",
        )
    with next(_scoped_session_cm(claims.firm_id)) as session:
        user = session.get(AppUser, uuid.UUID(claims.sub))
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="user not available",
            )
        _ = (user.id, user.firm_id, user.email, user.role, user.totp_confirmed)
        return user


def require_admin(user: AppUser = Depends(get_current_user)) -> AppUser:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required",
        )
    return user


# ---------------------------------------------------------------------------
# Small helper: contextmanager-y session opener returning a one-shot iterator
# so we can use it inside dependencies WITHOUT FastAPI seeing it as a nested
# dependency generator (which would confuse cleanup ordering).
# ---------------------------------------------------------------------------


def _scoped_session_cm(firm_id: str) -> Iterator[Session]:
    """Yields exactly one session; the caller uses ``with next(...)``."""
    from contextlib import contextmanager

    @contextmanager
    def _cm() -> Iterator[Session]:
        session = AppSessionLocal()
        try:
            session.begin()
            session.execute(
                text(
                    "SELECT set_config('app.current_firm_id', :firm_id, true)"
                ),
                {"firm_id": firm_id},
            )
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    yield _cm()
