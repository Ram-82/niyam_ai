"""/firm — firm-level preferences.

Read is available to any authenticated user in the firm (surfaces state
in the settings UI). Writes require admin.
"""
from __future__ import annotations

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


class FirmSettings(BaseModel):
    name: str
    plan: str
    reminders_enabled: bool


class FirmSettingsUpdate(BaseModel):
    reminders_enabled: bool | None = None


@router.get("/settings", response_model=FirmSettings)
def read_settings(
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> FirmSettings:
    row = session.execute(
        text(
            "SELECT name, plan, reminders_enabled "
            "FROM ca_firm WHERE id = :id"
        ),
        {"id": str(user.firm_id)},
    ).mappings().first()
    if row is None:
        # RLS + FK guarantee this shouldn't happen — but if it does,
        # a 500 is closer to the truth than a fabricated response.
        raise HTTPException(status_code=500, detail="firm row missing")
    return FirmSettings(
        name=row["name"],
        plan=row["plan"],
        reminders_enabled=bool(row["reminders_enabled"]),
    )


@router.patch("/settings", response_model=FirmSettings)
def update_settings(
    payload: FirmSettingsUpdate,
    admin: AppUser = Depends(require_admin),
    session=Depends(get_firm_scoped_session),
) -> FirmSettings:
    if payload.reminders_enabled is None:
        # No-op update; return current state.
        return read_settings(admin, session)

    result = session.execute(
        text(
            "UPDATE ca_firm SET reminders_enabled = :v WHERE id = :id"
        ),
        {"v": payload.reminders_enabled, "id": str(admin.firm_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=500, detail="firm row missing")
    audit.record(
        session=session,
        firm_id=admin.firm_id,
        actor_user_id=admin.id,
        action="firm.reminders_toggled",
        entity_type="ca_firm",
        entity_id=admin.firm_id,
        metadata={"reminders_enabled": payload.reminders_enabled},
    )
    return read_settings(admin, session)
