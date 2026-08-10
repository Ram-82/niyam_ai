"""Per-firm rule pack management — admin only.

Endpoints:

  GET    /rule-packs               — list packs for this firm
  POST   /rule-packs/clone         — clone the currently-active pack for
                                     this firm (inactive copy, firm-scoped)
  PATCH  /rule-packs/{id}          — update payload of a firm-specific pack
  POST   /rule-packs/{id}/activate — activate a firm-specific pack

Resolution: a firm-specific active pack overrides the global active pack
for all engine calls. A firm with no firm-specific pack uses the global
default.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import require_admin
from app.auth import audit
from app.db import firm_scoped_session, owner_engine
from app.models.tables import AppUser
from app.rules.pack import get_active_rule_pack


router = APIRouter(prefix="/rule-packs", tags=["rule-packs"])


class RulePackRow(BaseModel):
    id: str
    version: str
    active: bool
    firm_id: Optional[str]
    is_global: bool
    notes: Optional[str]
    created_at: Optional[datetime]


class RulePackDetail(RulePackRow):
    payload: dict[str, Any]


class CloneResponse(BaseModel):
    id: str
    version: str
    firm_id: str


class PayloadUpdate(BaseModel):
    payload: dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_packs_for_firm(firm_id: str) -> list[dict]:
    with owner_engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, version, active, firm_id, notes, created_at
                FROM rule_pack
                WHERE firm_id = :fid OR firm_id IS NULL
                ORDER BY
                    CASE WHEN firm_id = :fid THEN 0 ELSE 1 END,
                    active DESC,
                    created_at DESC
                """
            ),
            {"fid": firm_id},
        ).mappings().all()
    return [dict(r) for r in rows]


def _pack_belongs_to_firm(pack_id: str, firm_id: str) -> bool:
    with owner_engine.begin() as conn:
        row = conn.execute(
            text("SELECT firm_id FROM rule_pack WHERE id = :id"),
            {"id": pack_id},
        ).first()
    if row is None:
        return False
    return str(row[0]) == firm_id


# ---------------------------------------------------------------------------
# GET /rule-packs
# ---------------------------------------------------------------------------


@router.get("", response_model=list[RulePackRow])
def list_rule_packs(admin: AppUser = Depends(require_admin)) -> list[RulePackRow]:
    rows = _load_packs_for_firm(str(admin.firm_id))
    return [
        RulePackRow(
            id=str(r["id"]),
            version=r["version"],
            active=bool(r["active"]),
            firm_id=str(r["firm_id"]) if r["firm_id"] else None,
            is_global=r["firm_id"] is None,
            notes=r["notes"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# GET /rule-packs/{id}
# ---------------------------------------------------------------------------


@router.get("/{pack_id}", response_model=RulePackDetail)
def get_rule_pack(
    pack_id: uuid.UUID,
    admin: AppUser = Depends(require_admin),
) -> RulePackDetail:
    """Return a single pack (including full payload) visible to this firm."""
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                """
                SELECT id, version, active, firm_id, notes, created_at, payload
                FROM rule_pack
                WHERE id = :id
                  AND (firm_id = :fid OR firm_id IS NULL)
                """
            ),
            {"id": str(pack_id), "fid": str(admin.firm_id)},
        ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="rule pack not found")
    return RulePackDetail(
        id=str(row["id"]),
        version=row["version"],
        active=bool(row["active"]),
        firm_id=str(row["firm_id"]) if row["firm_id"] else None,
        is_global=row["firm_id"] is None,
        notes=row["notes"],
        created_at=row["created_at"],
        payload=dict(row["payload"]),
    )


# ---------------------------------------------------------------------------
# POST /rule-packs/clone
# ---------------------------------------------------------------------------


@router.post("/clone", response_model=CloneResponse, status_code=status.HTTP_201_CREATED)
def clone_active_pack(admin: AppUser = Depends(require_admin)) -> CloneResponse:
    """Clone the currently-active pack for this firm into a new firm-specific,
    inactive draft. The CA admin can then edit + activate it."""
    pack = get_active_rule_pack(firm_id=admin.firm_id)

    # Generate a child version slug: "1.0.0-firm-<firm-short>" so it's
    # distinct from the global semver and survives future global upgrades.
    short = str(admin.firm_id)[:8]
    new_version = f"{pack.version}-firm-{short}-{uuid.uuid4().hex[:6]}"

    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO rule_pack (version, payload, active, firm_id, notes)
                VALUES (:v, CAST(:p AS JSONB), FALSE, :fid, :notes)
                RETURNING id
                """
            ),
            {
                "v": new_version,
                "p": json.dumps(pack.payload),
                "fid": str(admin.firm_id),
                "notes": f"Cloned from {pack.version}",
            },
        )
        new_id = row.scalar_one()

    return CloneResponse(id=str(new_id), version=new_version, firm_id=str(admin.firm_id))


# ---------------------------------------------------------------------------
# PATCH /rule-packs/{id}
# ---------------------------------------------------------------------------


@router.patch("/{pack_id}", response_model=RulePackRow)
def update_payload(
    pack_id: uuid.UUID,
    body: PayloadUpdate,
    admin: AppUser = Depends(require_admin),
) -> RulePackRow:
    """Update the JSON payload of a firm-specific (inactive) pack."""
    if not _pack_belongs_to_firm(str(pack_id), str(admin.firm_id)):
        raise HTTPException(
            status_code=404, detail="rule pack not found or not editable"
        )

    with owner_engine.begin() as conn:
        # Reject edits to the currently-active pack — deactivate first.
        active = conn.execute(
            text("SELECT active FROM rule_pack WHERE id = :id"),
            {"id": str(pack_id)},
        ).scalar()
        if active:
            raise HTTPException(
                status_code=409,
                detail="cannot edit an active pack — clone it to create a new draft",
            )
        row = conn.execute(
            text(
                """
                UPDATE rule_pack
                SET payload = CAST(:p AS JSONB)
                WHERE id = :id
                RETURNING id, version, active, firm_id, notes, created_at
                """
            ),
            {"id": str(pack_id), "p": json.dumps(body.payload)},
        ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="rule pack not found")

    with firm_scoped_session(admin.firm_id) as db:
        audit.record(
            db,
            firm_id=admin.firm_id,
            actor_user_id=admin.id,
            action="rule_pack.payload_updated",
            entity_type="rule_pack",
            entity_id=pack_id,
            metadata={"pack_id": str(pack_id)},
        )
    return RulePackRow(
        id=str(row["id"]),
        version=row["version"],
        active=bool(row["active"]),
        firm_id=str(row["firm_id"]) if row["firm_id"] else None,
        is_global=row["firm_id"] is None,
        notes=row["notes"],
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# POST /rule-packs/{id}/activate
# ---------------------------------------------------------------------------


@router.post("/{pack_id}/activate", response_model=RulePackRow)
def activate_pack(
    pack_id: uuid.UUID,
    admin: AppUser = Depends(require_admin),
) -> RulePackRow:
    """Activate a firm-specific pack. Deactivates any previously active
    firm-specific pack for this firm (the global pack remains unchanged)."""
    if not _pack_belongs_to_firm(str(pack_id), str(admin.firm_id)):
        raise HTTPException(
            status_code=404, detail="rule pack not found or does not belong to this firm"
        )

    with owner_engine.begin() as conn:
        # Deactivate any other active firm-specific pack for this firm.
        conn.execute(
            text(
                "UPDATE rule_pack SET active = FALSE "
                "WHERE firm_id = :fid AND active = TRUE AND id != :id"
            ),
            {"fid": str(admin.firm_id), "id": str(pack_id)},
        )
        row = conn.execute(
            text(
                """
                UPDATE rule_pack SET active = TRUE WHERE id = :id
                RETURNING id, version, active, firm_id, notes, created_at
                """
            ),
            {"id": str(pack_id)},
        ).mappings().first()

    if row is None:
        raise HTTPException(status_code=404, detail="rule pack not found")

    with firm_scoped_session(admin.firm_id) as db:
        audit.record(
            db,
            firm_id=admin.firm_id,
            actor_user_id=admin.id,
            action="rule_pack.activated",
            entity_type="rule_pack",
            entity_id=pack_id,
            metadata={"pack_id": str(pack_id), "version": row["version"]},
        )
    return RulePackRow(
        id=str(row["id"]),
        version=row["version"],
        active=bool(row["active"]),
        firm_id=str(row["firm_id"]) if row["firm_id"] else None,
        is_global=row["firm_id"] is None,
        notes=row["notes"],
        created_at=row["created_at"],
    )
