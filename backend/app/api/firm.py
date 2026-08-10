"""/firm — firm-level preferences.

Read is available to any authenticated user in the firm (surfaces state
in the settings UI). Writes require admin.
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import (
    get_current_user,
    get_firm_scoped_session,
    require_admin,
)
from app.auth import audit
from app.models.tables import AppUser


router = APIRouter(prefix="/firm", tags=["firm"])

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class FirmSettings(BaseModel):
    name: str
    plan: str
    reminders_enabled: bool
    admin_whatsapp_number: Optional[str] = None


class FirmSettingsUpdate(BaseModel):
    reminders_enabled: Optional[bool] = None
    admin_whatsapp_number: Optional[str] = None  # empty string clears the field


@router.get("/settings", response_model=FirmSettings)
def read_settings(
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> FirmSettings:
    row = session.execute(
        text(
            "SELECT name, plan, reminders_enabled, admin_whatsapp_number "
            "FROM ca_firm WHERE id = :id"
        ),
        {"id": str(user.firm_id)},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=500, detail="firm row missing")
    return FirmSettings(
        name=row["name"],
        plan=row["plan"],
        reminders_enabled=bool(row["reminders_enabled"]),
        admin_whatsapp_number=row["admin_whatsapp_number"],
    )


@router.patch("/settings", response_model=FirmSettings)
def update_settings(
    payload: FirmSettingsUpdate,
    admin: AppUser = Depends(require_admin),
    session=Depends(get_firm_scoped_session),
) -> FirmSettings:
    if payload.reminders_enabled is None and payload.admin_whatsapp_number is None:
        return read_settings(admin, session)

    updates: dict = {}
    audit_meta: dict = {}

    if payload.reminders_enabled is not None:
        updates["reminders_enabled"] = payload.reminders_enabled
        audit_meta["reminders_enabled"] = payload.reminders_enabled

    if payload.admin_whatsapp_number is not None:
        number = payload.admin_whatsapp_number.strip() or None
        if number and not _E164_RE.match(number):
            raise HTTPException(
                status_code=422,
                detail="admin_whatsapp_number must be E.164 format (e.g. +919876543210)",
            )
        updates["admin_whatsapp_number"] = number
        audit_meta["admin_whatsapp_number"] = number

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    result = session.execute(
        text(f"UPDATE ca_firm SET {set_clause} WHERE id = :id"),
        {**updates, "id": str(admin.firm_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=500, detail="firm row missing")

    audit.record(
        session=session,
        firm_id=admin.firm_id,
        actor_user_id=admin.id,
        action="firm.settings_updated",
        entity_type="ca_firm",
        entity_id=admin.firm_id,
        metadata=audit_meta,
    )
    return read_settings(admin, session)
