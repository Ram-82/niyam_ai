"""Active rule pack loader.

Every engine output pins the ``rule_pack_version`` it was computed under
so historical results stay reproducible. This module is the single seam
that answers "which rule pack is active right now for a given firm?".

Resolution order in ``get_active_rule_pack(firm_id)``:
  1. Firm-specific active pack (WHERE firm_id = :fid AND active = TRUE)
  2. Global active pack        (WHERE firm_id IS NULL AND active = TRUE)

* ``rule_pack`` has RLS disabled — reads via owner_engine are safe from
  any context (workers with no firm scope, sweep, etc.).
* We do NOT cache the payload in a module-level variable — a hot-swap
  (INSERT new firm pack + activate) must be reflected in the next request.
  Reads are cheap: one indexed row per path.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy import text

from app.db import owner_engine


class NoActiveRulePackError(RuntimeError):
    """No row in ``rule_pack`` has ``active=TRUE`` — a broken deploy."""


@dataclass(frozen=True)
class RulePack:
    version: str
    payload: dict[str, Any]
    firm_id: Optional[str] = None  # None → global pack


def get_active_rule_pack(
    firm_id: "str | uuid.UUID | None" = None,
) -> RulePack:
    """Fetch the active rule pack for ``firm_id``, falling back to global.

    Pass ``firm_id=None`` (or omit it) to get the global pack — used in
    contexts where no firm is in scope (e.g. admin health checks).
    """
    with owner_engine.begin() as conn:
        if firm_id is not None:
            row = conn.execute(
                text(
                    "SELECT version, payload, firm_id "
                    "FROM rule_pack "
                    "WHERE firm_id = :fid AND active = TRUE LIMIT 1"
                ),
                {"fid": str(firm_id)},
            ).mappings().first()
            if row is not None:
                return RulePack(
                    version=row["version"],
                    payload=dict(row["payload"]),
                    firm_id=str(row["firm_id"]),
                )
        # Fall back to the global pack.
        row = conn.execute(
            text(
                "SELECT version, payload "
                "FROM rule_pack "
                "WHERE firm_id IS NULL AND active = TRUE LIMIT 1"
            )
        ).mappings().first()
    if row is None:
        raise NoActiveRulePackError(
            "no active rule_pack row — run `alembic upgrade head` "
            "or seed one via a data migration"
        )
    return RulePack(version=row["version"], payload=dict(row["payload"]))
