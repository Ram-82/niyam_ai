"""/audit-log — read the firm's immutable action log.

RLS-scoped by the session dependency; a caller can only ever see rows
whose ``firm_id`` matches their own. Writes are covered elsewhere
(app.auth.audit.record) and go through the same session; UPDATE + DELETE
are refused by triggers set up in migration 0001.

Filters are intentionally simple — entity type, entity id, action prefix
(``filing.*``), and a time window. Anything richer belongs in a proper
search index, not a compliance log.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import get_current_user, get_firm_scoped_session
from app.models.tables import AppUser


router = APIRouter(tags=["audit"])


class AuditRow(BaseModel):
    id: uuid.UUID
    firm_id: uuid.UUID
    user_id: Optional[uuid.UUID]
    action: str
    entity_type: str
    entity_id: Optional[uuid.UUID]
    diff: dict[str, Any]
    at: datetime
    user_email: Optional[str] = None


@router.get("/audit-log", response_model=list[AuditRow])
def list_audit(
    entity_type: Optional[str] = Query(default=None, max_length=64),
    entity_id: Optional[uuid.UUID] = None,
    action_prefix: Optional[str] = Query(default=None, max_length=64),
    user_id: Optional[uuid.UUID] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = Query(default=100, ge=1, le=500),
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> list[AuditRow]:
    where: list[str] = ["1 = 1"]
    params: dict[str, Any] = {"limit": limit}
    if entity_type:
        where.append("a.entity_type = :et")
        params["et"] = entity_type
    if entity_id:
        where.append("a.entity_id = :eid")
        params["eid"] = str(entity_id)
    if action_prefix:
        # Use LIKE with a literal prefix; not user-supplied SQL. The prefix
        # is bounded to 64 chars and passed as a bind param — no injection.
        where.append("a.action LIKE :ap")
        params["ap"] = f"{action_prefix}%"
    if user_id:
        where.append("a.user_id = :uid")
        params["uid"] = str(user_id)
    if since:
        where.append("a.at >= :since")
        params["since"] = since
    if until:
        where.append("a.at <= :until")
        params["until"] = until

    # LEFT JOIN so system rows (user_id NULL) still surface. app_user is
    # RLS-scoped too so the JOIN is naturally firm-safe.
    sql = (
        "SELECT a.id, a.firm_id, a.user_id, a.action, a.entity_type, "
        "a.entity_id, a.diff, a.at, u.email AS user_email "
        "FROM audit_log a "
        "LEFT JOIN app_user u ON u.id = a.user_id "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY a.at DESC LIMIT :limit"
    )
    rows = session.execute(text(sql), params).mappings().all()
    return [AuditRow(**dict(r)) for r in rows]
