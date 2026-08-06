"""/filings — generate and read GSTR-1/3B draft payloads.

* POST /filings/generate   — produce or regenerate a draft for
                             (gid, period, return_type)
* GET  /filings/{id}       — fetch one row (payload included)
* GET  /gstins/{gid}/filings?period=&return_type=
                             — list drafts for a GSTIN
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import get_current_user, get_firm_scoped_session
from app.filings.service import (
    FilingLocked,
    UnknownReturnType,
    generate_filing,
)
from app.models.tables import AppUser


router = APIRouter(tags=["filings"])


class GenerateReq(BaseModel):
    gstin_profile_id: uuid.UUID
    period: str = Field(pattern=r"^\d{6}$")
    return_type: str = Field(pattern=r"^(GSTR1|GSTR3B)$")


class FilingRow(BaseModel):
    id: uuid.UUID
    gstin_profile_id: uuid.UUID
    return_type: str
    period: str
    status: str
    rule_pack_version: str
    generated_by: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime
    payload: Optional[dict[str, Any]] = None


@router.post("/filings/generate", response_model=FilingRow)
def post_generate(
    body: GenerateReq,
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> FilingRow:
    try:
        row = generate_filing(
            session=session,
            firm_id=user.firm_id,
            gstin_profile_id=body.gstin_profile_id,
            period=body.period,
            return_type=body.return_type,
            user_id=user.id,
        )
    except FilingLocked as e:
        raise HTTPException(status_code=409, detail=str(e))
    except UnknownReturnType as e:
        raise HTTPException(status_code=400, detail=f"unknown_return_type: {e}")
    return FilingRow(**row)


@router.get("/filings/{filing_id}", response_model=FilingRow)
def get_one(
    filing_id: uuid.UUID,
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> FilingRow:
    row = session.execute(
        text(
            """
            SELECT id, gstin_profile_id, return_type, period, status,
                   rule_pack_version, generated_by, created_at, updated_at,
                   payload
              FROM filing_run
             WHERE id = :id
            """
        ),
        {"id": str(filing_id)},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="filing_not_found")
    return FilingRow(**dict(row))


@router.get("/gstins/{gstin_profile_id}/filings", response_model=list[FilingRow])
def list_for_gstin(
    gstin_profile_id: uuid.UUID,
    period: Optional[str] = Query(default=None, pattern=r"^\d{6}$"),
    return_type: Optional[str] = Query(default=None, pattern=r"^(GSTR1|GSTR3B)$"),
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> list[FilingRow]:
    where = ["gstin_profile_id = :gid"]
    params: dict[str, Any] = {"gid": str(gstin_profile_id)}
    if period:
        where.append("period = :p")
        params["p"] = period
    if return_type:
        where.append("return_type = :rt")
        params["rt"] = return_type
    sql = (
        "SELECT id, gstin_profile_id, return_type, period, status, "
        "rule_pack_version, generated_by, created_at, updated_at, payload "
        "FROM filing_run "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY updated_at DESC LIMIT 200"
    )
    rows = session.execute(text(sql), params).mappings().all()
    return [FilingRow(**dict(r)) for r in rows]
