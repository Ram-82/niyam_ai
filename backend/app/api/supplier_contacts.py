"""/supplier-contacts — firm-scoped supplier directory.

Endpoint map:
* GET    /supplier-contacts                      list + optional search
* GET    /supplier-contacts/by-gstin/{gstin}     lookup for prefill
* POST   /supplier-contacts                      create
* PATCH  /supplier-contacts/{id}                 update
* DELETE /supplier-contacts/{id}                 hard delete

All are RLS-scoped and either-role. Mutations audit.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_current_user, get_firm_scoped_session
from app.auth import audit
from app.models.tables import AppUser


router = APIRouter(prefix="/supplier-contacts", tags=["supplier-contacts"])


_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")
# Loose GSTIN validation — 15 chars, alphanumeric. Full checksum is on
# the invoice ingest path; here we only need to reject obvious garbage.
_GSTIN_RE = re.compile(r"^[0-9A-Z]{15}$")


class SupplierContactRow(BaseModel):
    id: uuid.UUID
    supplier_gstin: str
    name: str
    whatsapp_number: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
    created_by: Optional[uuid.UUID] = None
    created_at: datetime
    updated_by: Optional[uuid.UUID] = None
    updated_at: datetime


class CreateReq(BaseModel):
    supplier_gstin: str = Field(min_length=15, max_length=15)
    name: str = Field(min_length=1, max_length=200)
    whatsapp_number: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = Field(default=None, max_length=1000)


class UpdateReq(BaseModel):
    """Every field optional — PATCH semantics."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    whatsapp_number: Optional[str] = Field(default=None, max_length=20)
    email: Optional[str] = Field(default=None, max_length=255)
    notes: Optional[str] = Field(default=None, max_length=1000)


def _validate_input(gstin: str, whatsapp_number: Optional[str]) -> None:
    if not _GSTIN_RE.match(gstin.upper()):
        raise HTTPException(status_code=400, detail="invalid_gstin")
    if whatsapp_number is not None and whatsapp_number != "" and not _E164_RE.match(whatsapp_number):
        raise HTTPException(status_code=400, detail="invalid_e164_number")


@router.get("", response_model=list[SupplierContactRow])
def list_contacts(
    user: AppUser = Depends(get_current_user),
    q: Optional[str] = Query(
        default=None,
        description="Case-insensitive substring match against name and gstin.",
    ),
    limit: int = Query(default=100, ge=1, le=500),
    session=Depends(get_firm_scoped_session),
) -> list[SupplierContactRow]:
    sql = (
        "SELECT id, supplier_gstin, name, whatsapp_number, email, notes, "
        "created_by, created_at, updated_by, updated_at "
        "FROM supplier_contact "
        "WHERE firm_id = :fid"
    )
    params: dict = {"fid": str(user.firm_id), "limit": limit}
    if q:
        sql += (
            " AND (name ILIKE :q OR supplier_gstin ILIKE :q)"
        )
        params["q"] = f"%{q}%"
    sql += " ORDER BY name ASC LIMIT :limit"
    rows = session.execute(text(sql), params).mappings().all()
    return [SupplierContactRow(**dict(r)) for r in rows]


@router.get(
    "/by-gstin/{supplier_gstin}",
    response_model=SupplierContactRow,
)
def get_by_gstin(
    supplier_gstin: str,
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> SupplierContactRow:
    """Powers the chase modal prefill. 404 when the GSTIN is unknown —
    the frontend treats that as "new supplier, CA types the details"."""
    row = session.execute(
        text(
            "SELECT id, supplier_gstin, name, whatsapp_number, email, notes, "
            "created_by, created_at, updated_by, updated_at "
            "FROM supplier_contact "
            "WHERE supplier_gstin = :g"
        ),
        {"g": supplier_gstin.upper()},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="supplier_contact_not_found")
    return SupplierContactRow(**dict(row))


@router.post("", response_model=SupplierContactRow, status_code=status.HTTP_201_CREATED)
def create_contact(
    payload: CreateReq,
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> SupplierContactRow:
    _validate_input(payload.supplier_gstin, payload.whatsapp_number)
    try:
        row = session.execute(
            text(
                """
                INSERT INTO supplier_contact (
                    firm_id, supplier_gstin, name, whatsapp_number, email,
                    notes, created_by, updated_by
                ) VALUES (
                    :fid, :g, :n, :wn, :em, :notes, :ub, :ub
                )
                RETURNING id, supplier_gstin, name, whatsapp_number, email,
                          notes, created_by, created_at, updated_by, updated_at
                """
            ),
            {
                "fid": str(user.firm_id),
                "g": payload.supplier_gstin.upper(),
                "n": payload.name,
                "wn": payload.whatsapp_number or None,
                "em": payload.email or None,
                "notes": payload.notes or None,
                "ub": str(user.id),
            },
        ).mappings().first()
    except IntegrityError as e:
        # (firm_id, supplier_gstin) uniqueness — surface as 409 with a
        # useful body so the frontend can offer "edit existing" instead.
        if "supplier_contact_firm_gstin_uniq" in str(e.orig):
            raise HTTPException(
                status_code=409, detail="supplier_gstin_already_in_directory"
            )
        raise
    assert row is not None
    contact = SupplierContactRow(**dict(row))
    audit.record(
        session,
        firm_id=user.firm_id,
        actor_user_id=user.id,
        action="supplier_contact.created",
        entity_type="supplier_contact",
        entity_id=contact.id,
        metadata={"supplier_gstin": contact.supplier_gstin, "name": contact.name},
    )
    return contact


@router.patch("/{contact_id}", response_model=SupplierContactRow)
def update_contact(
    contact_id: uuid.UUID,
    payload: UpdateReq,
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> SupplierContactRow:
    # Validate E.164 first if provided.
    if payload.whatsapp_number is not None and payload.whatsapp_number != "":
        if not _E164_RE.match(payload.whatsapp_number):
            raise HTTPException(status_code=400, detail="invalid_e164_number")
    # Build a dynamic SET clause so a PATCH only touches supplied fields.
    updates: list[str] = []
    params: dict = {"id": str(contact_id), "ub": str(user.id)}
    for field in ("name", "whatsapp_number", "email", "notes"):
        val = getattr(payload, field)
        if val is not None:
            updates.append(f"{field} = :{field}")
            params[field] = val if val != "" else None
    if not updates:
        # Nothing to change — return existing row unchanged.
        row = session.execute(
            text(
                "SELECT id, supplier_gstin, name, whatsapp_number, email, "
                "notes, created_by, created_at, updated_by, updated_at "
                "FROM supplier_contact WHERE id = :id"
            ),
            {"id": str(contact_id)},
        ).mappings().first()
        if row is None:
            raise HTTPException(status_code=404, detail="supplier_contact_not_found")
        return SupplierContactRow(**dict(row))
    updates.append("updated_by = :ub")
    updates.append("updated_at = now()")
    row = session.execute(
        text(
            "UPDATE supplier_contact "
            f"SET {', '.join(updates)} "
            "WHERE id = :id "
            "RETURNING id, supplier_gstin, name, whatsapp_number, email, "
            "          notes, created_by, created_at, updated_by, updated_at"
        ),
        params,
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="supplier_contact_not_found")
    contact = SupplierContactRow(**dict(row))
    audit.record(
        session,
        firm_id=user.firm_id,
        actor_user_id=user.id,
        action="supplier_contact.updated",
        entity_type="supplier_contact",
        entity_id=contact.id,
        metadata={
            "supplier_gstin": contact.supplier_gstin,
            "updated_fields": [
                f for f in ("name", "whatsapp_number", "email", "notes")
                if getattr(payload, f) is not None
            ],
        },
    )
    return contact


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_contact(
    contact_id: uuid.UUID,
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> None:
    row = session.execute(
        text(
            "DELETE FROM supplier_contact "
            "WHERE id = :id "
            "RETURNING supplier_gstin"
        ),
        {"id": str(contact_id)},
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="supplier_contact_not_found")
    audit.record(
        session,
        firm_id=user.firm_id,
        actor_user_id=user.id,
        action="supplier_contact.deleted",
        entity_type="supplier_contact",
        entity_id=contact_id,
        metadata={"supplier_gstin": row[0]},
    )
