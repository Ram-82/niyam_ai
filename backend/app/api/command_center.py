"""Command center — the endpoint the CA opens every morning of filing week.

Returns one row per (client × GSTIN × return_type) for the given period.
Each row carries the score, days to due date, ITC at risk (from the
recon summary's supplier_default total), and blockers count. If a
GSTIN has no snapshot yet, score/blockers come back as NULL so the
row still shows up — the CA needs to see "unscored" clients too.

Sort key on the response: (score ASC NULLS FIRST, days_to_due_date ASC).
The frontend can re-sort; server default matches prompt semantics:
"score ascending × deadline proximity."

Staff users only see clients they've been assigned. Admins see all
firm clients. RLS handles the firm boundary; the staff filter is an
extra WHERE EXISTS on client_assignment.
"""
from __future__ import annotations

import uuid
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import get_current_user, get_firm_scoped_session
from app.config import settings
from app.models.tables import AppUser
from app.rules.pack import get_active_rule_pack


router = APIRouter(prefix="/command-center", tags=["command-center"])


RETURN_TYPES = ("GSTR1", "GSTR3B")


class CommandCenterRow(BaseModel):
    client_id: uuid.UUID
    client_name: str
    gstin_profile_id: uuid.UUID
    gstin: str
    scheme: str
    return_type: str
    period: str
    score: Optional[int]
    days_to_due_date: Optional[int]
    itc_at_risk_paise: int
    blockers_count: int
    last_computed_at: Optional[datetime]


class CommandCenterResponse(BaseModel):
    period: str
    rows: list[CommandCenterRow]


@router.get("", response_model=CommandCenterResponse)
def command_center(
    period: Optional[str] = Query(None, pattern=r"^[0-9]{6}$"),
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> CommandCenterResponse:
    resolved_period = period or _default_period()
    pack = get_active_rule_pack()
    due_dates_cfg = pack.payload.get("scoring", {}).get("due_dates", {})

    is_staff = user.role == "staff"

    # Cross-join gstin × return_type so we always emit one row per pair,
    # then LEFT JOIN the latest snapshot + latest recon run for the period.
    sql = """
        WITH latest_snapshot AS (
            SELECT DISTINCT ON (gstin_profile_id, return_type)
                gstin_profile_id, return_type::text, period,
                score, blockers, computed_at
            FROM readiness_snapshot
            WHERE period = :period
            ORDER BY gstin_profile_id, return_type, computed_at DESC
        ),
        latest_recon AS (
            SELECT DISTINCT ON (gstin_profile_id)
                gstin_profile_id, summary
            FROM reconciliation_run
            WHERE period = :period AND status = 'completed'
            ORDER BY gstin_profile_id, created_at DESC
        )
        SELECT
            c.id AS client_id,
            c.trade_name AS client_name,
            gp.id AS gstin_profile_id,
            gp.gstin,
            gp.scheme::text AS scheme,
            rt.return_type,
            ls.score,
            ls.blockers,
            ls.computed_at,
            lr.summary AS recon_summary
        FROM client c
        JOIN gstin_profile gp ON gp.client_id = c.id
        CROSS JOIN (VALUES ('GSTR1'), ('GSTR3B')) rt(return_type)
        LEFT JOIN latest_snapshot ls
            ON ls.gstin_profile_id = gp.id
           AND ls.return_type = rt.return_type
        LEFT JOIN latest_recon lr ON lr.gstin_profile_id = gp.id
    """
    params: dict[str, Any] = {"period": resolved_period}
    if is_staff:
        sql += (
            " WHERE EXISTS (SELECT 1 FROM client_assignment ca "
            " WHERE ca.user_id = :uid AND ca.client_id = c.id)"
        )
        params["uid"] = str(user.id)
    sql += " ORDER BY c.trade_name, gp.gstin, rt.return_type"

    rows = session.execute(text(sql), params).mappings().all()
    tz = ZoneInfo(settings.display_tz)
    today = datetime.now(tz=tz).date()

    out: list[CommandCenterRow] = []
    for r in rows:
        due = _due_date(
            due_dates_cfg, r["return_type"], r["scheme"], resolved_period
        )
        days_remaining = (due - today).days if due else None

        recon = r["recon_summary"] or {}
        itc_at_risk = int(
            recon.get("supplier_default", {}).get("paise", 0)
        )
        blockers = r["blockers"] or []

        out.append(
            CommandCenterRow(
                client_id=r["client_id"],
                client_name=r["client_name"],
                gstin_profile_id=r["gstin_profile_id"],
                gstin=r["gstin"],
                scheme=r["scheme"],
                return_type=r["return_type"],
                period=resolved_period,
                score=int(r["score"]) if r["score"] is not None else None,
                days_to_due_date=days_remaining,
                itc_at_risk_paise=itc_at_risk,
                blockers_count=len(blockers),
                last_computed_at=r["computed_at"],
            )
        )

    # Server-side sort: score ascending (NULLs first so unscored surfaces
    # at the top), then days_to_due_date ascending (nearest deadline first).
    out.sort(
        key=lambda row: (
            (0, 0) if row.score is None else (1, row.score),
            999 if row.days_to_due_date is None else row.days_to_due_date,
        )
    )
    return CommandCenterResponse(period=resolved_period, rows=out)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _default_period() -> str:
    """Last complete calendar month in Asia/Kolkata (or whatever display TZ)."""
    tz = ZoneInfo(settings.display_tz)
    today = datetime.now(tz=tz).date()
    first_of_this_month = today.replace(day=1)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    return f"{last_of_prev_month.year:04d}{last_of_prev_month.month:02d}"


def _due_date(
    cfg: dict, return_type: str, scheme: str, period: str
) -> Optional[date]:
    """Same computation as scoring.service — kept co-located here to avoid
    a cross-package import for a small helper. Consolidate if it grows."""
    ret_cfg = cfg.get(return_type, {})
    day = ret_cfg.get(scheme)
    if day is None:
        return None
    year, month = int(period[:4]), int(period[4:])
    y, m = (year + 1, 1) if month == 12 else (year, month + 1)
    day = min(int(day), monthrange(y, m)[1])
    return date(y, m, day)
