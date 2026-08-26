"""/reports/* — aggregated firm-scoped analytics.

For P1 we only ship the timeliness aggregation (on-time vs late filings
per month per return type). Other KPIs on the reports page derive from
existing endpoints (command-center, firm/health-summary, filings list).

Due dates come from the firm's active rule pack (falling back to the
global pack, then to the statutory defaults GSTR-1=11th / GSTR-3B=20th
of the following month). This matches ``app.narrator.facts_builder``.
"""
from __future__ import annotations

from calendar import month_abbr
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import get_current_user, get_firm_scoped_session
from app.models.tables import AppUser
from app.rules.pack import get_active_rule_pack

router = APIRouter(prefix="/reports", tags=["reports"])


class MonthlyTimeliness(BaseModel):
    period: str            # YYYYMM
    label: str             # "Sep 2026"
    gstr1_filed: int
    gstr1_on_time: int
    gstr3b_filed: int
    gstr3b_on_time: int


class TimelinessResponse(BaseModel):
    period_from: str
    period_to: str
    months: list[MonthlyTimeliness]
    total_filed: int
    total_on_time: int


def _default_window() -> tuple[str, str]:
    """Trailing 12 months ending in the current month."""
    today = date.today()
    y, m = today.year, today.month
    end = f"{y}{m:02d}"
    # 11 months back so the window is 12 months inclusive.
    back_m = m - 11
    back_y = y
    while back_m <= 0:
        back_m += 12
        back_y -= 1
    start = f"{back_y}{back_m:02d}"
    return start, end


def _enumerate_periods(period_from: str, period_to: str) -> list[str]:
    """Inclusive monthly enumeration YYYYMM → YYYYMM (start ≤ end)."""
    fy, fm = int(period_from[:4]), int(period_from[4:])
    ty, tm = int(period_to[:4]), int(period_to[4:])
    out: list[str] = []
    y, m = fy, fm
    while (y, m) <= (ty, tm):
        out.append(f"{y}{m:02d}")
        m += 1
        if m == 13:
            m = 1
            y += 1
        if len(out) > 240:  # 20-year safety net
            break
    return out


def _due_date_for(return_type: str, period: str, due_cfg: dict) -> Optional[date]:
    """Return the statutory due date, or None if the return type isn't
    covered. QRMP and non-monthly cadences fall through to None → excluded
    from the on-time calc (they still count towards `total_filed`)."""
    if len(period) != 6 or not period.isdigit():
        return None
    y, m = int(period[:4]), int(period[4:])
    if m == 12:
        fy, fm = y + 1, 1
    else:
        fy, fm = y, m + 1
    if return_type == "GSTR1":
        day = int(due_cfg.get("gstr1_monthly", 11))
    elif return_type == "GSTR3B":
        day = int(due_cfg.get("gstr3b_monthly", 20))
    else:
        return None
    try:
        return date(fy, fm, day)
    except ValueError:
        return None


def _label(period: str) -> str:
    y, m = int(period[:4]), int(period[4:])
    return f"{month_abbr[m]} {y}"


PERIOD_RE = r"^\d{6}$"


@router.get("/timeliness", response_model=TimelinessResponse)
def timeliness(
    period_from: Optional[str] = Query(default=None, pattern=PERIOD_RE),
    period_to: Optional[str] = Query(default=None, pattern=PERIOD_RE),
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> TimelinessResponse:
    """On-time vs total filed, per (period, return_type) in the window.

    The "filed at" timestamp is the earliest ``filing.marked_filed``
    audit row for the filing_run. A filing is on-time iff the calendar
    date of that timestamp is ≤ the statutory due date of its period.

    Only filings with status='filed' are counted. Drafts / approved are
    ignored — timeliness is a completion metric.
    """
    if period_from is None or period_to is None:
        start, end = _default_window()
        period_from = period_from or start
        period_to = period_to or end
    if period_from > period_to:
        raise HTTPException(status_code=400, detail="period_from must be ≤ period_to")

    pack = get_active_rule_pack(firm_id=str(user.firm_id))
    due_cfg = (pack.payload.get("statutory") or {}).get("due_dates") or {}

    # Join filing_run to audit_log for the mark-filed timestamp. GROUP BY
    # in a CTE so multiple audit rows for the same filing (defensive:
    # shouldn't happen but doesn't cost extra) collapse to the earliest.
    sql = text(
        """
        WITH mark_filed AS (
            SELECT entity_id::uuid AS filing_id, MIN(at) AS filed_at
            FROM audit_log
            WHERE action = 'filing.marked_filed'
              AND entity_type = 'filing_run'
              AND entity_id IS NOT NULL
            GROUP BY entity_id
        )
        SELECT fr.period, fr.return_type::text AS return_type,
               (mf.filed_at AT TIME ZONE 'Asia/Kolkata')::date AS filed_on
        FROM filing_run fr
        LEFT JOIN mark_filed mf ON mf.filing_id = fr.id
        WHERE fr.status = 'filed'
          AND fr.period BETWEEN :pf AND :pt
        """
    )
    rows = session.execute(sql, {"pf": period_from, "pt": period_to}).mappings().all()

    # Bucket into per-period-per-return-type counters.
    buckets: dict[str, dict[str, int]] = {}
    for r in rows:
        period = str(r["period"])
        rtype = str(r["return_type"])
        filed_on: Optional[date] = r["filed_on"]
        b = buckets.setdefault(period, {"g1_f": 0, "g1_on": 0, "g3_f": 0, "g3_on": 0})
        if rtype == "GSTR1":
            b["g1_f"] += 1
        elif rtype == "GSTR3B":
            b["g3_f"] += 1
        due = _due_date_for(rtype, period, due_cfg)
        # "On time" requires both a known due date and a recorded filed_at.
        # If filed_on is NULL the status was flipped without going through
        # the mark_filed audit path — treat as late (backend never does this
        # but seed data / manual DB ops might).
        if due is not None and filed_on is not None and filed_on <= due:
            if rtype == "GSTR1":
                b["g1_on"] += 1
            elif rtype == "GSTR3B":
                b["g3_on"] += 1

    months: list[MonthlyTimeliness] = []
    total_filed = 0
    total_on_time = 0
    for p in _enumerate_periods(period_from, period_to):
        b = buckets.get(p, {"g1_f": 0, "g1_on": 0, "g3_f": 0, "g3_on": 0})
        row = MonthlyTimeliness(
            period=p,
            label=_label(p),
            gstr1_filed=b["g1_f"],
            gstr1_on_time=b["g1_on"],
            gstr3b_filed=b["g3_f"],
            gstr3b_on_time=b["g3_on"],
        )
        months.append(row)
        total_filed += row.gstr1_filed + row.gstr3b_filed
        total_on_time += row.gstr1_on_time + row.gstr3b_on_time

    return TimelinessResponse(
        period_from=period_from,
        period_to=period_to,
        months=months,
        total_filed=total_filed,
        total_on_time=total_on_time,
    )
