"""Thin wrapper for appending to ``audit_log``.

The audit_log table is APPEND ONLY: grants permit SELECT + INSERT only and
two BEFORE triggers reject UPDATE/DELETE. This helper always issues the
INSERT via an RLS-scoped session — the caller opens the session pinned to
the correct firm and passes it in.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session


def record(
    session: Session,
    firm_id: uuid.UUID | str,
    actor_user_id: Optional[uuid.UUID | str],
    action: str,
    entity_type: str,
    entity_id: Optional[uuid.UUID | str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    """Append a single audit row inside ``session``'s open transaction.

    The caller is responsible for committing. Passing ``metadata=None``
    stores an empty JSONB object.
    """
    import json

    session.execute(
        text(
            """
            INSERT INTO audit_log (
                firm_id, user_id, action, entity_type, entity_id, diff
            ) VALUES (
                :firm_id, :user_id, :action, :entity_type, :entity_id,
                CAST(:diff AS JSONB)
            )
            """
        ),
        {
            "firm_id": str(firm_id),
            "user_id": str(actor_user_id) if actor_user_id else None,
            "action": action,
            "entity_type": entity_type,
            "entity_id": str(entity_id) if entity_id else None,
            "diff": json.dumps(metadata or {}),
        },
    )
