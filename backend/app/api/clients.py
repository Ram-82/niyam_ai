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

import csv
import io
import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import get_current_user, get_firm_scoped_session, require_admin
from app.auth import audit
from app.legal.gate import require_legal_accepted
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
    _legal: None = Depends(require_legal_accepted),
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
    _legal: None = Depends(require_legal_accepted),
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


# ---------------------------------------------------------------------------
# POST /clients/import — bulk CSV import (admin only)
# ---------------------------------------------------------------------------

# Field names the CSV can map to. Each row creates a Client; if a `gstin`
# is provided, a GstinProfile is also created for that client.
IMPORT_FIELDS = {
    "trade_name",         # required
    "gstin",              # optional — creates gstin_profile if provided
    "state_code",         # required if gstin provided; derived from GSTIN[:2] if omitted
    "scheme",             # optional; regular|composition; defaults to "regular"
    "language",           # optional; defaults to "en"
    "whatsapp_number",    # optional; must be E.164
}

# Case-insensitive keyword → field-name suggestions for auto-mapping.
# Longest-first so "state_code" beats "state" when both would match.
_AUTOMAP_HINTS: list[tuple[str, str]] = [
    ("trade_name", "trade_name"),
    ("trade name", "trade_name"),
    ("client name", "trade_name"),
    ("legal name", "trade_name"),
    ("business name", "trade_name"),
    ("name", "trade_name"),
    ("gstin_primary", "gstin"),
    ("gst_number", "gstin"),
    ("gst number", "gstin"),
    ("gstin", "gstin"),
    ("gst", "gstin"),
    ("state_code", "state_code"),
    ("state code", "state_code"),
    ("state", "state_code"),
    ("scheme", "scheme"),
    ("business_type", "scheme"),
    ("business type", "scheme"),
    ("language", "language"),
    ("lang", "language"),
    ("whatsapp_number", "whatsapp_number"),
    ("whatsapp", "whatsapp_number"),
    ("phone_mobile", "whatsapp_number"),
    ("phone", "whatsapp_number"),
    ("mobile", "whatsapp_number"),
    ("contact", "whatsapp_number"),
]


def _auto_map(headers: list[str]) -> dict[str, str]:
    """Return {csv_header → field_name} best guess. Only assigns each
    field to one CSV column (first match wins)."""
    assigned: set[str] = set()
    out: dict[str, str] = {}
    for h in headers:
        norm = h.strip().lower()
        for pattern, field in _AUTOMAP_HINTS:
            if pattern in norm and field not in assigned:
                out[h] = field
                assigned.add(field)
                break
    return out


class ImportRowError(BaseModel):
    row: int
    message: str


class ImportResponse(BaseModel):
    total_rows: int
    column_headers: list[str]
    resolved_mapping: dict[str, str]
    preview: list[dict[str, str]]
    errors: list[ImportRowError]
    warnings: list[ImportRowError]
    created_clients: int
    created_gstins: int
    dry_run: bool


@router.post(
    "/import",
    response_model=ImportResponse,
    status_code=status.HTTP_200_OK,
)
async def import_clients_csv(
    file: UploadFile = File(...),
    mapping: str = Form(default="{}"),
    dry_run: bool = Query(default=True, description="If true, validate but do not insert."),
    admin: AppUser = Depends(require_admin),
    session=Depends(get_firm_scoped_session),
    _legal: None = Depends(require_legal_accepted),
) -> ImportResponse:
    # Parse mapping JSON.
    try:
        user_mapping: dict[str, str] = json.loads(mapping) if mapping else {}
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="mapping must be valid JSON")
    if not isinstance(user_mapping, dict):
        raise HTTPException(status_code=400, detail="mapping must be a JSON object")
    for k, v in user_mapping.items():
        if v and v not in IMPORT_FIELDS:
            raise HTTPException(
                status_code=400,
                detail=f"mapping targets unknown field: {v!r} (allowed: {sorted(IMPORT_FIELDS)})",
            )

    # Read the CSV. Accept BOM + \r\n line endings.
    raw = await file.read()
    if len(raw) == 0:
        raise HTTPException(status_code=400, detail="empty file")
    if len(raw) > 5 * 1024 * 1024:  # 5 MB cap — CA firm client lists are small.
        raise HTTPException(status_code=413, detail="file too large (5 MB max)")
    try:
        text_body = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="file must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text_body))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row")
    headers = [h.strip() for h in reader.fieldnames]

    # Resolve mapping: user's overrides win over auto-detected suggestions.
    resolved = _auto_map(headers)
    for k, v in user_mapping.items():
        if k in headers:
            if v:
                resolved[k] = v
            else:
                resolved.pop(k, None)  # explicit "skip this column"

    inverse: dict[str, str] = {}
    for csv_col, field in resolved.items():
        if field in inverse:
            raise HTTPException(
                status_code=400,
                detail=f"field {field!r} mapped from more than one column",
            )
        inverse[field] = csv_col

    if "trade_name" not in inverse:
        raise HTTPException(
            status_code=400,
            detail="'trade_name' is required — no CSV column maps to it",
        )

    errors: list[ImportRowError] = []
    warnings: list[ImportRowError] = []
    preview: list[dict[str, str]] = []
    to_insert: list[dict] = []
    total_rows = 0

    for i, raw_row in enumerate(reader, start=2):  # start=2: row 1 is the header
        total_rows += 1
        row = {k.strip(): (v or "").strip() for k, v in raw_row.items() if k}
        mapped: dict[str, str] = {}
        for field, csv_col in inverse.items():
            mapped[field] = row.get(csv_col, "")

        # Skip empty rows entirely.
        if not any(mapped.values()):
            warnings.append(ImportRowError(row=i, message="row is empty; skipped"))
            continue

        # Required: trade_name.
        if not mapped.get("trade_name"):
            errors.append(ImportRowError(row=i, message="trade_name is required"))
            continue

        # Optional: gstin — if provided, must be structural + state_code derivable.
        gstin = mapped.get("gstin", "").upper() if mapped.get("gstin") else ""
        state_code = mapped.get("state_code", "")
        if gstin:
            if not GSTIN_STRUCTURAL_RE.match(gstin):
                errors.append(ImportRowError(row=i, message=f"gstin {gstin!r} fails structural format"))
                continue
            if not state_code:
                state_code = gstin[:2]
                warnings.append(ImportRowError(row=i, message=f"state_code derived from GSTIN as {state_code!r}"))
            elif state_code != gstin[:2]:
                errors.append(ImportRowError(
                    row=i,
                    message=f"state_code {state_code!r} disagrees with GSTIN prefix {gstin[:2]!r}",
                ))
                continue

        scheme = (mapped.get("scheme") or "regular").lower()
        if scheme not in ("regular", "composition"):
            errors.append(ImportRowError(row=i, message=f"scheme must be regular|composition, got {scheme!r}"))
            continue

        language = mapped.get("language") or "en"
        whatsapp = mapped.get("whatsapp_number") or None
        if whatsapp and not _E164_RE.match(whatsapp):
            errors.append(ImportRowError(row=i, message=f"whatsapp_number {whatsapp!r} must be E.164 (e.g. +919812345678)"))
            continue

        record = {
            "row": i,
            "trade_name": mapped["trade_name"],
            "gstin": gstin or None,
            "state_code": state_code or None,
            "scheme": scheme,
            "language": language,
            "whatsapp_number": whatsapp,
        }
        to_insert.append(record)
        if len(preview) < 5:
            preview.append({k: str(v) if v is not None else "" for k, v in record.items()})

    created_clients = 0
    created_gstins = 0
    if not dry_run and to_insert:
        for rec in to_insert:
            client_id = uuid.uuid4()
            try:
                session.execute(
                    text(
                        "INSERT INTO client (id, firm_id, trade_name, language, whatsapp_number) "
                        "VALUES (:id, :firm_id, :name, :lang, :wn)"
                    ),
                    {
                        "id": str(client_id),
                        "firm_id": str(admin.firm_id),
                        "name": rec["trade_name"],
                        "lang": rec["language"],
                        "wn": rec["whatsapp_number"],
                    },
                )
                created_clients += 1
                audit.record(
                    session,
                    firm_id=admin.firm_id,
                    actor_user_id=admin.id,
                    action="client.created",
                    entity_type="client",
                    entity_id=client_id,
                    metadata={"source": "csv_import", "after": {"trade_name": rec["trade_name"]}},
                )
                if rec["gstin"]:
                    gid = uuid.uuid4()
                    try:
                        session.execute(
                            text(
                                "INSERT INTO gstin_profile "
                                "(id, firm_id, client_id, gstin, state_code, scheme) "
                                "VALUES (:id, :firm_id, :cid, :gstin, :sc, CAST(:scheme AS gst_scheme))"
                            ),
                            {
                                "id": str(gid),
                                "firm_id": str(admin.firm_id),
                                "cid": str(client_id),
                                "gstin": rec["gstin"],
                                "sc": rec["state_code"],
                                "scheme": rec["scheme"],
                            },
                        )
                        created_gstins += 1
                    except Exception as e:
                        if "gstin_profile_client_gstin_uniq" in str(e):
                            warnings.append(ImportRowError(
                                row=rec["row"],
                                message=f"client created but gstin {rec['gstin']} already exists on another client",
                            ))
                        else:
                            raise
            except Exception as e:
                errors.append(ImportRowError(
                    row=rec["row"],
                    message=f"insert failed: {type(e).__name__}",
                ))

    return ImportResponse(
        total_rows=total_rows,
        column_headers=headers,
        resolved_mapping=resolved,
        preview=preview,
        errors=errors,
        warnings=warnings,
        created_clients=created_clients,
        created_gstins=created_gstins,
        dry_run=dry_run,
    )
