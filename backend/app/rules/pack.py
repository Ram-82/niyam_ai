"""Active rule pack loader.

Every engine output pins the ``rule_pack_version`` it was computed under
so historical results stay reproducible. This module is the single seam
that answers "which rule pack is active right now?".

* Rule_pack is a global table (not tenant-scoped). All firms see the
  same active version. Multi-tenant per-firm rule packs are a P2/P3
  question we'll cross when it comes up.
* One row can be active at a time — the partial unique index
  ``rule_pack_single_active`` in ``0001_initial`` enforces it.
* We deliberately do NOT cache the payload in a module-level variable —
  a hot-swap (INSERT new, flip active) should be reflected in the next
  request. If profiling shows this is a hot path we'll add a short TTL
  cache. Reads are cheap: one indexed row.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.db import owner_engine


class NoActiveRulePackError(RuntimeError):
    """No row in ``rule_pack`` has ``active=TRUE`` — a broken deploy."""


@dataclass(frozen=True)
class RulePack:
    version: str
    payload: dict[str, Any]


def get_active_rule_pack() -> RulePack:
    """Fetch the currently-active rule pack. Raises if none.

    Reads through the owner engine — ``rule_pack`` has RLS disabled (see
    migration 0001) so the app role's grants are SELECT-only, and this
    call is safe from any context (including workers with no firm scope).
    """
    with owner_engine.begin() as conn:
        row = conn.execute(
            text("SELECT version, payload FROM rule_pack WHERE active = TRUE LIMIT 1")
        ).mappings().first()
    if row is None:
        raise NoActiveRulePackError(
            "no active rule_pack row — run `alembic upgrade head` "
            "or seed one via a data migration"
        )
    return RulePack(version=row["version"], payload=dict(row["payload"]))
