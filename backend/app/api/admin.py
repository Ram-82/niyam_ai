"""Firm settings — admin-only. Staff management + client assignments.

Endpoints:

  GET    /users                                       — list firm users
  POST   /assignments {user_id, client_id}            — assign client
  DELETE /assignments/{user_id}/{client_id}           — unassign

All mutations audited.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import get_firm_scoped_session, require_admin
from app.auth import audit
from app.models.tables import AppUser


router = APIRouter(tags=["admin"])


class UserRow(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    totp_confirmed: bool


@router.get("/users", response_model=list[UserRow])
def list_users(
    _: AppUser = Depends(require_admin),
    session=Depends(get_firm_scoped_session),
) -> list[UserRow]:
    rows = session.execute(
        text(
            "SELECT id, email, role::text, is_active, totp_confirmed "
            "FROM app_user ORDER BY email"
        )
    ).mappings().all()
    return [
        UserRow(
            id=r["id"],
            email=str(r["email"]),
            role=r["role"],
            is_active=r["is_active"],
            totp_confirmed=r["totp_confirmed"],
        )
        for r in rows
    ]


class AssignRequest(BaseModel):
    user_id: uuid.UUID
    client_id: uuid.UUID


@router.post(
    "/assignments",
    status_code=status.HTTP_201_CREATED,
)
def create_assignment(
    payload: AssignRequest,
    admin: AppUser = Depends(require_admin),
    session=Depends(get_firm_scoped_session),
) -> dict:
    # Assert both user and client exist within this firm (RLS filters, so
    # a missing row surfaces as a clean 404).
    if not session.execute(
        text("SELECT 1 FROM app_user WHERE id = :u"),
        {"u": str(payload.user_id)},
    ).scalar():
        raise HTTPException(status_code=404, detail="user not found")
    if not session.execute(
        text("SELECT 1 FROM client WHERE id = :c"),
        {"c": str(payload.client_id)},
    ).scalar():
        raise HTTPException(status_code=404, detail="client not found")
    try:
        session.execute(
            text(
                "INSERT INTO client_assignment "
                "(firm_id, user_id, client_id) "
                "VALUES (:f, :u, :c)"
            ),
            {
                "f": str(admin.firm_id),
                "u": str(payload.user_id),
                "c": str(payload.client_id),
            },
        )
    except Exception as e:
        if "client_assignment_pkey" in str(e):
            raise HTTPException(status_code=409, detail="already assigned")
        raise
    audit.record(
        session,
        firm_id=admin.firm_id,
        actor_user_id=admin.id,
        action="assignment.granted",
        entity_type="client_assignment",
        entity_id=None,
        metadata={
            "after": {
                "user_id": str(payload.user_id),
                "client_id": str(payload.client_id),
            }
        },
    )
    return {"user_id": str(payload.user_id), "client_id": str(payload.client_id)}


@router.delete(
    "/assignments/{user_id}/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_assignment(
    user_id: uuid.UUID,
    client_id: uuid.UUID,
    admin: AppUser = Depends(require_admin),
    session=Depends(get_firm_scoped_session),
) -> None:
    result = session.execute(
        text(
            "DELETE FROM client_assignment "
            "WHERE user_id = :u AND client_id = :c"
        ),
        {"u": str(user_id), "c": str(client_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="assignment not found")
    audit.record(
        session,
        firm_id=admin.firm_id,
        actor_user_id=admin.id,
        action="assignment.revoked",
        entity_type="client_assignment",
        entity_id=None,
        metadata={
            "before": {
                "user_id": str(user_id),
                "client_id": str(client_id),
            }
        },
    )
