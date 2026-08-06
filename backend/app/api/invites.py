"""/invites endpoints (admin only).

Every path is protected by ``require_admin`` and every DB touch runs inside
a firm-scoped session, so RLS auto-scopes invite reads and writes to the
admin's own firm.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select, text, update

from app.api.deps import get_firm_scoped_session, require_admin
from app.auth import audit
from app.auth.service import hash_invite_token
from app.config import settings
from app.email import send_invite_email
from app.models.tables import UserInvite, AppUser


logger = logging.getLogger(__name__)


router = APIRouter(prefix="/invites", tags=["invites"])


class InviteCreateRequest(BaseModel):
    email: EmailStr
    role: str = Field(pattern="^(admin|staff)$")
    ttl_hours: int = Field(default=72, gt=0, le=24 * 30)


class InviteCreateResponse(BaseModel):
    invite_id: uuid.UUID
    invite_token: str  # raw token — shown ONCE
    expires_at: datetime


class InviteListItem(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    accepted_at: Optional[datetime]
    created_at: datetime


@router.post(
    "/",
    response_model=InviteCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_invite(
    payload: InviteCreateRequest,
    admin: AppUser = Depends(require_admin),
    session=Depends(get_firm_scoped_session),
) -> InviteCreateResponse:
    raw = secrets.token_urlsafe(32)
    token_hash = hash_invite_token(raw)
    expires_at = datetime.now(tz=timezone.utc) + timedelta(hours=payload.ttl_hours)

    invite = UserInvite(
        firm_id=admin.firm_id,
        email=payload.email,
        role=payload.role,
        token_hash=token_hash,
        invited_by=admin.id,
        expires_at=expires_at,
    )
    session.add(invite)
    session.flush()

    email_sent = False
    if settings.email_enabled:
        firm_name = session.execute(
            text("SELECT name FROM ca_firm WHERE id = :id"),
            {"id": str(admin.firm_id)},
        ).scalar() or ""
        try:
            send_invite_email(
                to=payload.email,
                invite_token=raw,
                inviter_email=str(admin.email),
                firm_name=firm_name,
                role=payload.role,
                expires_at=expires_at,
            )
            email_sent = True
        except Exception as exc:
            # An email transport failure MUST NOT rollback the invite.
            # The invite_token is returned to the admin either way, and
            # the copy-URL UI is the contract-guaranteed fallback.
            logger.warning(
                "invite.email_dispatch_failed",
                extra={"invite_id": str(invite.id), "error": str(exc)},
            )

    audit.record(
        session=session,
        firm_id=admin.firm_id,
        actor_user_id=admin.id,
        action="invite.created",
        entity_type="user_invite",
        entity_id=invite.id,
        metadata={"email": payload.email, "role": payload.role, "email_sent": email_sent},
    )
    return InviteCreateResponse(
        invite_id=invite.id, invite_token=raw, expires_at=expires_at
    )


@router.get("/", response_model=list[InviteListItem])
def list_invites(
    _: AppUser = Depends(require_admin),
    session=Depends(get_firm_scoped_session),
) -> list[InviteListItem]:
    rows = session.execute(select(UserInvite)).scalars().all()
    return [
        InviteListItem(
            id=r.id,
            email=str(r.email),
            role=r.role,
            expires_at=r.expires_at,
            accepted_at=r.accepted_at,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.delete("/{invite_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_invite(
    invite_id: uuid.UUID,
    admin: AppUser = Depends(require_admin),
    session=Depends(get_firm_scoped_session),
) -> None:
    # Soft-delete by expiring in place. Keeps the row for audit but makes
    # subsequent /register attempts fail on expiry.
    now = datetime.now(tz=timezone.utc)
    result = session.execute(
        update(UserInvite)
        .where(UserInvite.id == invite_id)
        .values(expires_at=now)
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="invite not found")
    audit.record(
        session=session,
        firm_id=admin.firm_id,
        actor_user_id=admin.id,
        action="invite.revoked",
        entity_type="user_invite",
        entity_id=invite_id,
        metadata={},
    )
    return None
