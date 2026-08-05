"""/narrator endpoints — generate + list prior runs.

* POST /narrator/preview          — generate narration for (gstin, period, return_type)
* GET  /narrator/runs             — list recent narration_run rows for the firm

The narration itself is intermediate — a CA reviews and edits before the
WhatsApp delivery layer sends it. This API does NOT deliver; delivery is
gated by the CA-approval + delivery surfaces (P3 scope).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import get_current_user, get_firm_scoped_session
from app.models.tables import AppUser
from app.narrator import service
from app.narrator.facts_builder import FactsUnavailable
from app.narrator.types import (
    Language,
    NarratorDisabled,
    NarratorError,
    NumberHallucination,
)


router = APIRouter(prefix="/narrator", tags=["narrator"])


class PreviewReq(BaseModel):
    gstin_profile_id: uuid.UUID
    period: str = Field(pattern=r"^\d{6}$")
    return_type: str = Field(pattern=r"^(GSTR1|GSTR3B)$")
    language: str = Field(default="en", pattern=r"^(en|hi|kn|mr)$")


class PreviewResp(BaseModel):
    narration_run_id: uuid.UUID
    provider: str
    model: str
    language: str
    page1_health: str
    page1_tax_position: str
    page2_attention: str
    page2_ask_your_ca: str


class NarrationRunRow(BaseModel):
    id: uuid.UUID
    gstin_profile_id: uuid.UUID
    return_type: str
    period: str
    language: str
    provider: str
    model: str
    generated_at: datetime


@router.post("/preview", response_model=PreviewResp)
def preview(
    payload: PreviewReq,
    user: AppUser = Depends(get_current_user),
) -> PreviewResp:
    try:
        output, run_id = service.narrate_for_period(
            firm_id=user.firm_id,
            gstin_profile_id=payload.gstin_profile_id,
            return_type=payload.return_type,
            period=payload.period,
            language=payload.language,  # type: ignore[arg-type]
            user_id=user.id,
        )
    except NarratorDisabled:
        raise HTTPException(status_code=503, detail="narrator_disabled")
    except FactsUnavailable:
        raise HTTPException(
            status_code=409,
            detail="no_readiness_snapshot",
        )
    except NumberHallucination:
        # Two consecutive hallucinations — bail loudly. The CA sees a
        # retry surface; we do NOT return partial prose.
        raise HTTPException(
            status_code=502,
            detail="narrator_number_hallucination",
        )
    except NarratorError as e:
        raise HTTPException(status_code=502, detail=f"narrator_error: {e}")
    return PreviewResp(
        narration_run_id=run_id,
        provider=output.provider,
        model=output.model,
        language=output.language,
        page1_health=output.page1_health,
        page1_tax_position=output.page1_tax_position,
        page2_attention=output.page2_attention,
        page2_ask_your_ca=output.page2_ask_your_ca,
    )


@router.get("/runs", response_model=list[NarrationRunRow])
def list_runs(
    user: AppUser = Depends(get_current_user),
    gstin_profile_id: Optional[uuid.UUID] = None,
    period: Optional[str] = Query(default=None, pattern=r"^\d{6}$"),
    limit: int = Query(default=50, ge=1, le=200),
    session=Depends(get_firm_scoped_session),
) -> list[NarrationRunRow]:
    where = ["firm_id = :fid"]
    params: dict = {"fid": str(user.firm_id), "limit": limit}
    if gstin_profile_id:
        where.append("gstin_profile_id = :gpid")
        params["gpid"] = str(gstin_profile_id)
    if period:
        where.append("period = :p")
        params["p"] = period
    sql = (
        "SELECT id, gstin_profile_id, return_type, period, language, "
        "provider, model, generated_at "
        "FROM narration_run "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY generated_at DESC LIMIT :limit"
    )
    rows = session.execute(text(sql), params).mappings().all()
    return [NarrationRunRow(**dict(r)) for r in rows]
