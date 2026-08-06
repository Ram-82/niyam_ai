"""/calendar — upcoming GSTR-1 / GSTR-3B due dates for the caller's firm.

Read-only surface backed by the same due-date compute the reminder
sweep uses. The endpoint returns every (gid × return_type × period)
whose due date falls in ``[today - lookback, today + horizon]``, joined
with any existing ``filing_run.status`` and a count of sent reminders.

Frontend renders this as a grouped table (this week / next week /
later / recently past).
"""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import get_current_user, get_firm_scoped_session
from app.models.tables import AppUser
from app.rules.pack import get_active_rule_pack


router = APIRouter(tags=["calendar"])


RETURN_TYPES: tuple[str, ...] = ("GSTR1", "GSTR3B")


class CalendarRow(BaseModel):
    gstin_profile_id: str
    gstin: str
    client_id: str
    client_trade_name: str
    scheme: str
    return_type: str
    period: str
    due_date: date
    days_out: int  # negative = overdue
    filing_status: Optional[str]  # 'draft' | 'approved' | 'filed' | None
    reminders_sent: int


class CalendarResponse(BaseModel):
    today: date
    horizon_days: int
    lookback_days: int
    rows: list[CalendarRow]


def _compute_due_date(
    due_cfg: dict, return_type: str, scheme: str, period: str
) -> Optional[date]:
    day = (due_cfg.get(return_type) or {}).get(scheme)
    if day is None:
        return None
    year, month = int(period[:4]), int(period[4:])
    if month == 12:
        y, m = year + 1, 1
    else:
        y, m = year, month + 1
    day = min(int(day), monthrange(y, m)[1])
    return date(y, m, day)


def _candidate_periods(today: date, lookback_days: int, horizon_days: int) -> list[str]:
    """Enumerate every YYYYMM whose due date could plausibly land in the
    [today-lookback, today+horizon] window.

    Due date lives in the month FOLLOWING the period, so we look back
    (lookback+horizon)/30 + 2 months from ``today`` — small margin so
    we never miss a candidate at month edges.
    """
    def _prev(y: int, m: int, n: int) -> tuple[int, int]:
        m -= n
        while m < 1:
            m += 12
            y -= 1
        return y, m

    span_months = (lookback_days + horizon_days) // 30 + 2
    out = []
    for n in range(span_months):
        y, m = _prev(today.year, today.month, n)
        out.append(f"{y:04d}{m:02d}")
    return out


@router.get("/calendar/upcoming", response_model=CalendarResponse)
def upcoming(
    horizon_days: int = Query(default=45, ge=1, le=180),
    lookback_days: int = Query(default=14, ge=0, le=90),
    _: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> CalendarResponse:
    today = datetime.now(tz=timezone.utc).date()

    # 1. Every active GID visible to the caller (RLS scopes this).
    gids = session.execute(
        text(
            """
            SELECT gp.id::text        AS gstin_profile_id,
                   gp.gstin           AS gstin,
                   gp.client_id::text AS client_id,
                   gp.scheme::text    AS scheme,
                   c.trade_name       AS client_trade_name
            FROM gstin_profile gp
            LEFT JOIN client c ON c.id = gp.client_id
            """
        )
    ).mappings().all()
    if not gids:
        return CalendarResponse(
            today=today, horizon_days=horizon_days,
            lookback_days=lookback_days, rows=[],
        )

    pack = get_active_rule_pack()
    due_cfg = (pack.payload.get("scoring", {}) or {}).get("due_dates", {}) or {}

    # 2. Precompute the period → return_type → filing_status map and
    # reminder counts in a single query each, so we don't hit N+1.
    gid_ids = [g["gstin_profile_id"] for g in gids]
    periods = _candidate_periods(today, lookback_days, horizon_days)

    fr_map: dict[tuple[str, str, str], str] = {}
    for row in session.execute(
        text(
            """
            SELECT gstin_profile_id::text AS gid,
                   period,
                   return_type::text AS return_type,
                   status::text AS status
            FROM filing_run
            WHERE gstin_profile_id = ANY(:gids)
              AND period = ANY(:periods)
            """
        ),
        {"gids": gid_ids, "periods": list(periods)},
    ).mappings():
        fr_map[(row["gid"], row["period"], row["return_type"])] = row["status"]

    rem_map: dict[tuple[str, str, str], int] = {}
    for row in session.execute(
        text(
            """
            SELECT gstin_profile_id::text AS gid,
                   period,
                   return_type::text AS return_type,
                   count(*) FILTER (WHERE sent_at IS NOT NULL) AS n
            FROM reminder_log
            WHERE gstin_profile_id = ANY(:gids)
              AND period = ANY(:periods)
            GROUP BY 1, 2, 3
            """
        ),
        {"gids": gid_ids, "periods": list(periods)},
    ).mappings():
        rem_map[(row["gid"], row["period"], row["return_type"])] = int(row["n"])

    # 3. Assemble the response.
    rows: list[CalendarRow] = []
    for g in gids:
        for return_type in RETURN_TYPES:
            for period in periods:
                due = _compute_due_date(due_cfg, return_type, g["scheme"], period)
                if due is None:
                    continue
                days_out = (due - today).days
                if days_out < -lookback_days or days_out > horizon_days:
                    continue
                key = (g["gstin_profile_id"], period, return_type)
                rows.append(CalendarRow(
                    gstin_profile_id=g["gstin_profile_id"],
                    gstin=g["gstin"],
                    client_id=g["client_id"],
                    client_trade_name=g["client_trade_name"] or "",
                    scheme=g["scheme"],
                    return_type=return_type,
                    period=period,
                    due_date=due,
                    days_out=days_out,
                    filing_status=fr_map.get(key),
                    reminders_sent=rem_map.get(key, 0),
                ))
    rows.sort(key=lambda r: (r.due_date, r.return_type, r.gstin))
    return CalendarResponse(
        today=today, horizon_days=horizon_days,
        lookback_days=lookback_days, rows=rows,
    )
