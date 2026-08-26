"""/firm — firm-level preferences and dashboard aggregates.

Read is available to any authenticated user in the firm (surfaces state
in the settings UI). Writes require admin. Dashboard aggregates
(``/firm/health-summary``, ``/firm/recent-activity``) are read-only
firm-scoped rollups used by the v2 dashboard.
"""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import (
    get_current_user,
    get_firm_scoped_session,
    require_admin,
)
from app.auth import audit
from app.models.tables import AppUser
from app.rules.pack import get_active_rule_pack


router = APIRouter(prefix="/firm", tags=["firm"])

_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class FirmSettings(BaseModel):
    name: str
    plan: str
    reminders_enabled: bool
    narrator_enabled: bool
    admin_whatsapp_number: Optional[str] = None


class FirmSettingsUpdate(BaseModel):
    reminders_enabled: Optional[bool] = None
    narrator_enabled: Optional[bool] = None
    admin_whatsapp_number: Optional[str] = None  # empty string clears the field


@router.get("/settings", response_model=FirmSettings)
def read_settings(
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> FirmSettings:
    row = session.execute(
        text(
            "SELECT name, plan, reminders_enabled, narrator_enabled, "
            "admin_whatsapp_number "
            "FROM ca_firm WHERE id = :id"
        ),
        {"id": str(user.firm_id)},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=500, detail="firm row missing")
    return FirmSettings(
        name=row["name"],
        plan=row["plan"],
        reminders_enabled=bool(row["reminders_enabled"]),
        narrator_enabled=bool(row["narrator_enabled"]),
        admin_whatsapp_number=row["admin_whatsapp_number"],
    )


@router.patch("/settings", response_model=FirmSettings)
def update_settings(
    payload: FirmSettingsUpdate,
    admin: AppUser = Depends(require_admin),
    session=Depends(get_firm_scoped_session),
) -> FirmSettings:
    if (
        payload.reminders_enabled is None
        and payload.narrator_enabled is None
        and payload.admin_whatsapp_number is None
    ):
        return read_settings(admin, session)

    updates: dict = {}
    audit_meta: dict = {}

    if payload.reminders_enabled is not None:
        updates["reminders_enabled"] = payload.reminders_enabled
        audit_meta["reminders_enabled"] = payload.reminders_enabled

    if payload.narrator_enabled is not None:
        updates["narrator_enabled"] = payload.narrator_enabled
        audit_meta["narrator_enabled"] = payload.narrator_enabled

    if payload.admin_whatsapp_number is not None:
        number = payload.admin_whatsapp_number.strip() or None
        if number and not _E164_RE.match(number):
            raise HTTPException(
                status_code=422,
                detail="admin_whatsapp_number must be E.164 format (e.g. +919876543210)",
            )
        updates["admin_whatsapp_number"] = number
        audit_meta["admin_whatsapp_number"] = number

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    result = session.execute(
        text(f"UPDATE ca_firm SET {set_clause} WHERE id = :id"),
        {**updates, "id": str(admin.firm_id)},
    )
    if result.rowcount == 0:
        raise HTTPException(status_code=500, detail="firm row missing")

    audit.record(
        session=session,
        firm_id=admin.firm_id,
        actor_user_id=admin.id,
        action="firm.settings_updated",
        entity_type="ca_firm",
        entity_id=admin.firm_id,
        metadata=audit_meta,
    )
    return read_settings(admin, session)


# ---------------------------------------------------------------------------
# Dashboard aggregates
# ---------------------------------------------------------------------------


class HealthDistribution(BaseModel):
    healthy: int          # clients whose latest snapshots are all green
    due_soon: int         # any filing due within 7 days & not filed
    overdue_blocked: int  # any overdue filing OR score < 60 OR blockers > 0


class FirmHealthSummary(BaseModel):
    score: Optional[int]              # mean of latest readiness_snapshot.score
    prev_score: Optional[int]         # ~30d ago comparison (None if no history)
    active_clients_count: int
    distribution: HealthDistribution
    last_computed_at: Optional[datetime]


@router.get("/health-summary", response_model=FirmHealthSummary)
def firm_health_summary(
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> FirmHealthSummary:
    """Firm-wide compliance score + client bucket distribution.

    Score is the mean of the latest ``readiness_snapshot.score`` for every
    (gid × return_type) pair visible to the caller. Clients bucket into
    healthy / due_soon / overdue_blocked based on their worst status
    across all their GIDs. RLS scopes to the caller's firm.
    """
    today = datetime.now(tz=timezone.utc).date()

    # Latest snapshot per (gid, return_type) — plus every visible client
    # and gstin_profile so we can bucket even clients with no snapshot.
    # We also pull the snapshot's period so overdue/due_soon can be
    # computed against a period this GID was actually expected to file
    # (rather than every historical period, which would mark brand-new
    # clients as overdue for pre-registration windows).
    rows = session.execute(
        text(
            """
            WITH latest_snapshot AS (
                SELECT DISTINCT ON (gstin_profile_id, return_type)
                    gstin_profile_id, return_type::text AS return_type,
                    period, score, blockers, computed_at
                FROM readiness_snapshot
                ORDER BY gstin_profile_id, return_type, computed_at DESC
            )
            SELECT
                c.id::text                         AS client_id,
                gp.id::text                        AS gid,
                gp.scheme::text                    AS scheme,
                ls.return_type                     AS return_type,
                ls.period                          AS period,
                ls.score                           AS score,
                ls.blockers                        AS blockers,
                ls.computed_at                     AS computed_at
            FROM client c
            JOIN gstin_profile gp ON gp.client_id = c.id
            LEFT JOIN latest_snapshot ls ON ls.gstin_profile_id = gp.id
            """
        )
    ).mappings().all()

    # For overdue detection we need due dates from the rule pack + filing
    # statuses. Small firms → fine to walk in Python; if this grows
    # heavy, push into the SQL above.
    pack = get_active_rule_pack()
    due_cfg = (pack.payload.get("scoring", {}) or {}).get("due_dates", {}) or {}

    filings = session.execute(
        text(
            """
            SELECT gstin_profile_id::text AS gid,
                   period,
                   return_type::text AS return_type,
                   status::text AS status
            FROM filing_run
            """
        )
    ).mappings().all()
    filing_status: dict[tuple[str, str, str], str] = {
        (r["gid"], r["period"], r["return_type"]): r["status"] for r in filings
    }

    # Build per-client bucket.
    clients: dict[str, dict[str, Any]] = {}
    scores: list[int] = []
    last_ts: Optional[datetime] = None

    for r in rows:
        cid = r["client_id"]
        entry = clients.setdefault(
            cid, {"scores": [], "blockers": 0, "overdue": False, "due_soon": False}
        )
        if r["score"] is not None:
            s = int(r["score"])
            entry["scores"].append(s)
            scores.append(s)
        if r["blockers"]:
            entry["blockers"] += len(r["blockers"])
        if r["computed_at"] and (last_ts is None or r["computed_at"] > last_ts):
            last_ts = r["computed_at"]

    # Compute overdue / due_soon per client using the LATEST scored
    # period per (gid × return_type). Semantics: a client is at risk
    # only for filings we've already scored — we don't assume
    # obligations for historical periods where the client had no
    # activity in the system.
    from calendar import monthrange

    def _due_date(rt: str, scheme: str, period: str) -> Optional[date]:
        day = (due_cfg.get(rt) or {}).get(scheme)
        if day is None:
            return None
        year, month = int(period[:4]), int(period[4:])
        y, m = (year + 1, 1) if month == 12 else (year, month + 1)
        return date(y, m, min(int(day), monthrange(y, m)[1]))

    for r in rows:
        if r["period"] is None:
            continue  # gid has no snapshot yet; nothing to score
        cid = r["client_id"]
        entry = clients.get(cid)
        if entry is None:
            continue
        due = _due_date(r["return_type"], r["scheme"], r["period"])
        if due is None:
            continue
        status_ = filing_status.get((r["gid"], r["period"], r["return_type"]))
        if status_ == "filed":
            continue
        days_out = (due - today).days
        if days_out < 0:
            entry["overdue"] = True
        elif days_out <= 7:
            entry["due_soon"] = True

    healthy = due_soon = overdue = 0
    for entry in clients.values():
        worst_score = min(entry["scores"]) if entry["scores"] else None
        if entry["overdue"] or entry["blockers"] > 0 or (
            worst_score is not None and worst_score < 60
        ):
            overdue += 1
        elif entry["due_soon"]:
            due_soon += 1
        else:
            healthy += 1

    score = int(round(sum(scores) / len(scores))) if scores else None

    # Prev score — mean of scores from snapshots computed 25-35 days ago.
    window_start = today - timedelta(days=35)
    window_end = today - timedelta(days=25)
    prev_rows = session.execute(
        text(
            """
            SELECT AVG(score)::float AS avg_score
            FROM (
                SELECT DISTINCT ON (gstin_profile_id, return_type)
                    score
                FROM readiness_snapshot
                WHERE computed_at::date BETWEEN :ws AND :we
                ORDER BY gstin_profile_id, return_type, computed_at DESC
            ) prev
            """
        ),
        {"ws": window_start, "we": window_end},
    ).mappings().first()
    prev_score = (
        int(round(prev_rows["avg_score"]))
        if prev_rows and prev_rows["avg_score"] is not None
        else None
    )

    return FirmHealthSummary(
        score=score,
        prev_score=prev_score,
        active_clients_count=len(clients),
        distribution=HealthDistribution(
            healthy=healthy,
            due_soon=due_soon,
            overdue_blocked=overdue,
        ),
        last_computed_at=last_ts,
    )


class RecentActivityItem(BaseModel):
    id: uuid.UUID
    at: datetime
    action: str
    tone: str  # 'success' | 'danger' | 'neutral'
    icon: str  # 'check' | 'alert' | 'upload' | 'message' | 'settings'
    title: str
    subtitle: Optional[str] = None
    actor_email: Optional[str] = None


_ACTION_TONE = {
    "filing.filed": ("success", "check"),
    "filing.approved": ("success", "check"),
    "filing.marked_filed": ("success", "check"),
    "filing.generated": ("neutral", "upload"),
    "match.confirmed": ("success", "check"),
    "match.rejected": ("neutral", "message"),
    "flag.resolved": ("success", "check"),
    "flag.raised": ("danger", "alert"),
    "reminder.sent": ("neutral", "message"),
    "firm.settings_updated": ("neutral", "settings"),
    "import.completed": ("neutral", "upload"),
    "narrator.generated": ("neutral", "message"),
}


@router.get("/recent-activity", response_model=list[RecentActivityItem])
def firm_recent_activity(
    limit: int = Query(default=6, ge=1, le=50),
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> list[RecentActivityItem]:
    """Recent firm activity feed — audit_log enriched with entity labels.

    RLS scopes to caller's firm. Entity display resolution is best-effort:
    unresolvable entity_ids fall back to the entity_type label.
    """
    audit_rows = session.execute(
        text(
            """
            SELECT a.id, a.at, a.action, a.entity_type, a.entity_id,
                   a.diff, u.email AS user_email
            FROM audit_log a
            LEFT JOIN app_user u ON u.id = a.user_id
            ORDER BY a.at DESC
            LIMIT :lim
            """
        ),
        {"lim": limit},
    ).mappings().all()

    # Bulk-fetch labels for filing_run / gstin_profile / client entities.
    filing_ids = [r["entity_id"] for r in audit_rows if r["entity_type"] == "filing_run" and r["entity_id"]]
    filing_labels: dict[str, tuple[str, str, str]] = {}
    if filing_ids:
        for row in session.execute(
            text(
                """
                SELECT fr.id::text AS id, c.trade_name AS client_name,
                       fr.return_type::text AS return_type, fr.period AS period
                FROM filing_run fr
                JOIN gstin_profile gp ON gp.id = fr.gstin_profile_id
                JOIN client c ON c.id = gp.client_id
                WHERE fr.id = ANY(:ids)
                """
            ),
            {"ids": [str(i) for i in filing_ids]},
        ).mappings():
            filing_labels[row["id"]] = (row["client_name"], row["return_type"], row["period"])

    out: list[RecentActivityItem] = []
    for r in audit_rows:
        action = str(r["action"])
        tone, icon = _ACTION_TONE.get(action, ("neutral", "message"))
        # Longest-prefix fallback for unknown fine-grained actions.
        if action not in _ACTION_TONE:
            for prefix, mapped in _ACTION_TONE.items():
                if action.startswith(prefix.split(".")[0] + "."):
                    tone, icon = mapped
                    break

        title = _humanize_action(action)
        subtitle: Optional[str] = None
        if r["entity_type"] == "filing_run" and r["entity_id"]:
            label = filing_labels.get(str(r["entity_id"]))
            if label:
                client_name, return_type, period = label
                subtitle = f"{client_name} · {return_type} · {_fmt_period(period)}"
        elif r["entity_type"] == "ca_firm":
            subtitle = "Firm settings"
        elif r["entity_type"]:
            subtitle = r["entity_type"].replace("_", " ").title()

        out.append(RecentActivityItem(
            id=r["id"],
            at=r["at"],
            action=action,
            tone=tone,
            icon=icon,
            title=title,
            subtitle=subtitle,
            actor_email=r["user_email"],
        ))
    return out


def _humanize_action(action: str) -> str:
    """`filing.marked_filed` → `Filing marked filed`."""
    parts = action.replace(".", " ").replace("_", " ").split()
    if not parts:
        return action
    return parts[0].capitalize() + (" " + " ".join(parts[1:]) if len(parts) > 1 else "")


def _fmt_period(period: str) -> str:
    """`202607` → `Jul 2026`."""
    if len(period) != 6 or not period.isdigit():
        return period
    year, month = int(period[:4]), int(period[4:])
    from calendar import month_abbr
    return f"{month_abbr[month]} {year}"
