"""Client + GSTIN CRUD.

Reads are firm-scoped via RLS. Writes are admin-only and audited.
Staff can list assigned clients (filtered app-layer). The prompt's
positioning is "the CA firm is the tenant" — client rows are firm-
owned, so only admins create them.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import get_current_user, get_firm_scoped_session, require_admin
from app.auth import audit
from app.models.tables import AppUser


router = APIRouter(prefix="/clients", tags=["clients"])


GSTIN_STRUCTURAL_RE = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z][A-Z][0-9A-Z]$"
)


_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class ClientCreateRequest(BaseModel):
    trade_name: str = Field(min_length=1, max_length=200)
    language: str = Field(default="en", max_length=8)
    whatsapp_number: Optional[str] = Field(default=None, max_length=20)


class ClientPatchRequest(BaseModel):
    """PATCH — every field optional; ``None`` means "leave as-is",
    empty-string on whatsapp_number means "clear it"."""
    trade_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    language: Optional[str] = Field(default=None, max_length=8)
    whatsapp_number: Optional[str] = Field(default=None, max_length=20)


class ClientResponse(BaseModel):
    id: uuid.UUID
    trade_name: str
    language: str
    whatsapp_number: Optional[str] = None


class ClientForGstinResponse(BaseModel):
    """Shape the workspace prefill wants: gstin + client details in
    one round trip so DeliveryPanel can render without a separate
    /clients round-trip."""
    gstin_profile_id: uuid.UUID
    gstin: str
    client_id: uuid.UUID
    trade_name: str
    language: str
    whatsapp_number: Optional[str] = None


class GstinCreateRequest(BaseModel):
    gstin: str
    state_code: str = Field(pattern=r"^[0-9]{2}$")
    scheme: str = Field(default="regular", pattern=r"^(regular|composition)$")


class GstinResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    gstin: str
    state_code: str
    scheme: str


# ---------------------------------------------------------------------------
# GET /clients — list (staff sees only assigned)
# ---------------------------------------------------------------------------


@router.get("", response_model=list[ClientResponse])
def list_clients(
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> list[ClientResponse]:
    sql = "SELECT id, trade_name, language, whatsapp_number FROM client"
    params: dict = {}
    if user.role == "staff":
        sql += (
            " WHERE EXISTS (SELECT 1 FROM client_assignment ca "
            " WHERE ca.user_id = :uid AND ca.client_id = client.id)"
        )
        params["uid"] = str(user.id)
    sql += " ORDER BY trade_name"
    rows = session.execute(text(sql), params).mappings().all()
    return [ClientResponse(**dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# POST /clients — admin only
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_client(
    payload: ClientCreateRequest,
    admin: AppUser = Depends(require_admin),
    session=Depends(get_firm_scoped_session),
) -> ClientResponse:
    if payload.whatsapp_number and not _E164_RE.match(payload.whatsapp_number):
        raise HTTPException(status_code=400, detail="invalid_e164_number")
    client_id = uuid.uuid4()
    session.execute(
        text(
            "INSERT INTO client (id, firm_id, trade_name, language, whatsapp_number) "
            "VALUES (:id, :firm_id, :name, :lang, :wn)"
        ),
        {
            "id": str(client_id),
            "firm_id": str(admin.firm_id),
            "name": payload.trade_name,
            "lang": payload.language,
            "wn": payload.whatsapp_number or None,
        },
    )
    audit.record(
        session,
        firm_id=admin.firm_id,
        actor_user_id=admin.id,
        action="client.created",
        entity_type="client",
        entity_id=client_id,
        metadata={
            "after": {
                "trade_name": payload.trade_name,
                "language": payload.language,
            }
        },
    )
    return ClientResponse(
        id=client_id,
        trade_name=payload.trade_name,
        language=payload.language,
        whatsapp_number=payload.whatsapp_number or None,
    )


@router.patch("/{client_id}", response_model=ClientResponse)
def patch_client(
    client_id: uuid.UUID,
    payload: ClientPatchRequest,
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> ClientResponse:
    """PATCH client fields (name, language, whatsapp_number).

    Non-admin can update this too — this endpoint is what the workspace
    calls when the CA opts into "save this number to the client record"
    after a delivery send. Restricting to admin would create a poor
    surface where every send needs an admin round-trip.
    """
    if payload.whatsapp_number and payload.whatsapp_number != "" and not _E164_RE.match(payload.whatsapp_number):
        raise HTTPException(status_code=400, detail="invalid_e164_number")
    updates: list[str] = []
    params: dict = {"id": str(client_id)}
    changed: dict = {}
    if payload.trade_name is not None:
        updates.append("trade_name = :trade_name")
        params["trade_name"] = payload.trade_name
        changed["trade_name"] = payload.trade_name
    if payload.language is not None:
        updates.append("language = :language")
        params["language"] = payload.language
        changed["language"] = payload.language
    if payload.whatsapp_number is not None:
        updates.append("whatsapp_number = :whatsapp_number")
        params["whatsapp_number"] = payload.whatsapp_number or None
        changed["whatsapp_number"] = payload.whatsapp_number or None
    if not updates:
        # No-op: return current row.
        row = session.execute(
            text(
                "SELECT id, trade_name, language, whatsapp_number "
                "FROM client WHERE id = :id"
            ),
            {"id": str(client_id)},
        ).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="client not found")
        return ClientResponse(**dict(row))
    row = session.execute(
        text(
            "UPDATE client "
            f"SET {', '.join(updates)} "
            "WHERE id = :id "
            "RETURNING id, trade_name, language, whatsapp_number"
        ),
        params,
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="client not found")
    audit.record(
        session,
        firm_id=user.firm_id,
        actor_user_id=user.id,
        action="client.updated",
        entity_type="client",
        entity_id=client_id,
        metadata={"after": changed},
    )
    return ClientResponse(**dict(row))


# ---------------------------------------------------------------------------
# POST /clients/{id}/gstins — admin only
# ---------------------------------------------------------------------------


@router.post(
    "/{client_id}/gstins",
    response_model=GstinResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_gstin(
    client_id: uuid.UUID,
    payload: GstinCreateRequest,
    admin: AppUser = Depends(require_admin),
    session=Depends(get_firm_scoped_session),
) -> GstinResponse:
    if not GSTIN_STRUCTURAL_RE.match(payload.gstin):
        raise HTTPException(
            status_code=422, detail="GSTIN fails structural format"
        )
    # Confirm client belongs to firm (RLS already filters, but a missing
    # row surfaces here as a clear 404 instead of a FK violation).
    exists = session.execute(
        text("SELECT 1 FROM client WHERE id = :id"),
        {"id": str(client_id)},
    ).scalar()
    if not exists:
        raise HTTPException(status_code=404, detail="client not found")

    gid = uuid.uuid4()
    try:
        session.execute(
            text(
                "INSERT INTO gstin_profile "
                "(id, firm_id, client_id, gstin, state_code, scheme) "
                "VALUES (:id, :firm_id, :cid, :gstin, :sc, "
                "  CAST(:scheme AS gst_scheme))"
            ),
            {
                "id": str(gid),
                "firm_id": str(admin.firm_id),
                "cid": str(client_id),
                "gstin": payload.gstin,
                "sc": payload.state_code,
                "scheme": payload.scheme,
            },
        )
    except Exception as e:
        # Uniqueness (client_id, gstin) surfaces as 409.
        if "gstin_profile_client_gstin_uniq" in str(e):
            raise HTTPException(
                status_code=409, detail="gstin already added to this client"
            )
        raise
    audit.record(
        session,
        firm_id=admin.firm_id,
        actor_user_id=admin.id,
        action="gstin.added",
        entity_type="gstin_profile",
        entity_id=gid,
        metadata={
            "after": {
                "client_id": str(client_id),
                "gstin": payload.gstin,
                "state_code": payload.state_code,
                "scheme": payload.scheme,
            }
        },
    )
    return GstinResponse(
        id=gid,
        client_id=client_id,
        gstin=payload.gstin,
        state_code=payload.state_code,
        scheme=payload.scheme,
    )
