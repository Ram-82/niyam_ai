"""DB integration for readiness scoring.

``compute_and_persist(firm_id, gstin_profile_id, return_type, period, today?)``:

1. Loads active rule pack (weights, due dates, curve).
2. Loads the latest reconciliation_run for the period (its summary
   drives every recon-derived blocker paise_impact).
3. Counts validation errors + warnings; sums impacted invoice paise.
4. Counts trailing 3-month + current-month invoices for data completeness.
5. Aggregates risky-supplier purchase paise for supplier_risk.
6. Computes days_to_due_date from rule pack + client scheme.
7. Calls the pure calculator.
8. Appends a row to ``readiness_snapshot`` (append-only).
9. Returns the ScoreResult + snapshot id.

Every rule pack lookup, due date, and weight comes from the active
rule_pack payload — nothing is hardcoded in the calculator's callers
either.
"""
from __future__ import annotations

import json
import uuid
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import firm_scoped_session
from app.engines.scoring.calculator import compute_score
from app.engines.scoring.types import ScoreInputs, ScoreResult
from app.rules.pack import get_active_rule_pack


TRAILING_MONTHS = 3


@dataclass
class ScoringRunResult:
    snapshot_id: uuid.UUID
    score: int
    blockers: list[dict[str, Any]]
    arithmetic: dict[str, Any]
    rule_pack_version: str


def compute_and_persist(
    firm_id: uuid.UUID | str,
    gstin_profile_id: uuid.UUID | str,
    return_type: str,
    period: str,
    today: Optional[date] = None,
) -> ScoringRunResult:
    pack = get_active_rule_pack()
    scoring_cfg = pack.payload.get("scoring", {})
    weights = scoring_cfg.get("weights", {})
    due_dates_cfg = scoring_cfg.get("due_dates", {})
    curve_days = int(
        scoring_cfg.get("days_to_due_date_curve", {}).get("full_score_days", 14)
    )

    tz = ZoneInfo(settings.display_tz)
    today = today or datetime.now(tz=tz).date()

    with firm_scoped_session(firm_id) as session:
        scheme = _lookup_scheme(session, gstin_profile_id)
        due = _due_date(due_dates_cfg, return_type, scheme, period)
        days_remaining = (due - today).days if due else 999

        invoice_count = _count_period_invoices(session, gstin_profile_id, period)
        errors, warnings = _flag_counts(session, gstin_profile_id, period)
        err_paise, warn_paise = _flag_paise(session, gstin_profile_id, period)

        summary, total_reg_paise = _recon_snapshot(
            session, gstin_profile_id, period
        )

        current_count, trailing_counts = _completeness_counts(
            session, gstin_profile_id, period
        )

        risky_paise, total_supplier_paise = _supplier_risk_paise(
            session, gstin_profile_id, period, summary
        )

    inputs = ScoreInputs(
        rule_pack_version=pack.version,
        weights=weights,
        days_to_due_date_curve_days=curve_days,
        return_type=return_type,
        period=period,
        today=today,
        invoice_count=invoice_count,
        validation_error_count=errors,
        validation_warning_count=warnings,
        recon_summary=summary,
        total_register_paise=total_reg_paise,
        trailing_month_counts=trailing_counts,
        current_month_count=current_count,
        risky_supplier_paise=risky_paise,
        total_supplier_paise=total_supplier_paise,
        days_to_due_date=days_remaining,
        error_invoice_paise=err_paise,
        warning_invoice_paise=warn_paise,
    )
    result: ScoreResult = compute_score(inputs)

    snapshot_id = _persist_snapshot(
        firm_id=firm_id,
        gstin_profile_id=gstin_profile_id,
        return_type=return_type,
        period=period,
        result=result,
    )

    return ScoringRunResult(
        snapshot_id=snapshot_id,
        score=result.score,
        blockers=[b.__dict__ for b in result.blockers],
        arithmetic=result.arithmetic,
        rule_pack_version=pack.version,
    )


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _lookup_scheme(session: Session, gstin_profile_id) -> str:
    row = session.execute(
        text("SELECT scheme::text FROM gstin_profile WHERE id = :id"),
        {"id": str(gstin_profile_id)},
    ).scalar()
    return row or "regular"


def _due_date(
    cfg: dict, return_type: str, scheme: str, period: str
) -> Optional[date]:
    ret_cfg = cfg.get(return_type, {})
    day = ret_cfg.get(scheme)
    if day is None:
        return None
    year, month = int(period[:4]), int(period[4:])
    # Due date is the given day of the FOLLOWING month.
    if month == 12:
        y, m = year + 1, 1
    else:
        y, m = year, month + 1
    # Clamp to last day of the target month.
    day = min(int(day), monthrange(y, m)[1])
    return date(y, m, day)


def _count_period_invoices(session: Session, gstin_profile_id, period: str) -> int:
    y, m = int(period[:4]), int(period[4:])
    return int(
        session.execute(
            text(
                "SELECT count(*) FROM invoice "
                "WHERE gstin_profile_id = :g "
                "  AND status = 'active' "
                "  AND EXTRACT(YEAR FROM invoice_date) = :y "
                "  AND EXTRACT(MONTH FROM invoice_date) = :m"
            ),
            {"g": str(gstin_profile_id), "y": y, "m": m},
        ).scalar()
        or 0
    )


def _flag_counts(session: Session, gstin_profile_id, period: str) -> tuple[int, int]:
    y, m = int(period[:4]), int(period[4:])
    rows = session.execute(
        text(
            """
            SELECT vf.severity::text, count(*)
            FROM validation_flag vf
            JOIN invoice i ON i.id = vf.invoice_id
            WHERE i.gstin_profile_id = :g
              AND vf.resolved = FALSE
              AND EXTRACT(YEAR FROM i.invoice_date) = :y
              AND EXTRACT(MONTH FROM i.invoice_date) = :m
            GROUP BY vf.severity
            """
        ),
        {"g": str(gstin_profile_id), "y": y, "m": m},
    ).fetchall()
    d = {sev: int(count) for sev, count in rows}
    return d.get("error", 0), d.get("warning", 0)


def _flag_paise(session: Session, gstin_profile_id, period: str) -> tuple[int, int]:
    """Sum of invoice.total_paise for invoices that have at least one
    unresolved error / warning flag. Same invoice counted once per
    severity even if it has multiple flags."""
    y, m = int(period[:4]), int(period[4:])
    rows = session.execute(
        text(
            """
            SELECT vf.severity::text, sum(i.total_paise)
            FROM (
                SELECT DISTINCT invoice_id, severity
                FROM validation_flag
                WHERE resolved = FALSE
            ) vf
            JOIN invoice i ON i.id = vf.invoice_id
            WHERE i.gstin_profile_id = :g
              AND EXTRACT(YEAR FROM i.invoice_date) = :y
              AND EXTRACT(MONTH FROM i.invoice_date) = :m
            GROUP BY vf.severity
            """
        ),
        {"g": str(gstin_profile_id), "y": y, "m": m},
    ).fetchall()
    d = {sev: int(paise or 0) for sev, paise in rows}
    return d.get("error", 0), d.get("warning", 0)


def _recon_snapshot(
    session: Session, gstin_profile_id, period: str
) -> tuple[dict, int]:
    """Latest reconciliation_run.summary for the period + total register paise.

    Empty dict if no run exists yet — the calculator handles the empty
    case (missed==0, everything falls to residual proportions).
    """
    y, m = int(period[:4]), int(period[4:])
    run_row = session.execute(
        text(
            "SELECT summary FROM reconciliation_run "
            "WHERE gstin_profile_id = :g AND period = :p "
            "  AND status = 'completed' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
        {"g": str(gstin_profile_id), "p": period},
    ).mappings().first()
    summary = dict(run_row["summary"]) if run_row else {}

    total = int(
        session.execute(
            text(
                "SELECT COALESCE(sum(total_paise), 0) FROM invoice "
                "WHERE gstin_profile_id = :g "
                "  AND direction = 'purchase' "
                "  AND status = 'active' "
                "  AND EXTRACT(YEAR FROM invoice_date) = :y "
                "  AND EXTRACT(MONTH FROM invoice_date) = :m"
            ),
            {"g": str(gstin_profile_id), "y": y, "m": m},
        ).scalar()
        or 0
    )
    return summary, total


def _completeness_counts(
    session: Session, gstin_profile_id, period: str
) -> tuple[int, list[int]]:
    current_count = _count_period_invoices(session, gstin_profile_id, period)
    trailing: list[int] = []
    y, m = int(period[:4]), int(period[4:])
    for offset in range(1, TRAILING_MONTHS + 1):
        ty, tm = _months_back(y, m, offset)
        trailing.append(
            int(
                session.execute(
                    text(
                        "SELECT count(*) FROM invoice "
                        "WHERE gstin_profile_id = :g "
                        "  AND status = 'active' "
                        "  AND EXTRACT(YEAR FROM invoice_date) = :y "
                        "  AND EXTRACT(MONTH FROM invoice_date) = :m"
                    ),
                    {"g": str(gstin_profile_id), "y": ty, "m": tm},
                ).scalar()
                or 0
            )
        )
    return current_count, list(reversed(trailing))  # oldest first


def _months_back(year: int, month: int, n: int) -> tuple[int, int]:
    total = year * 12 + (month - 1) - n
    return divmod(total, 12)[0], divmod(total, 12)[1] + 1


def _trailing_recon_summaries(
    session: Session,
    gstin_profile_id,
    period: str,
    n: int = TRAILING_MONTHS,
) -> list[dict]:
    """Latest completed reconciliation_run summary for each of the n periods
    before ``period``. Returns an empty list for any period with no run."""
    y, m = int(period[:4]), int(period[4:])
    summaries: list[dict] = []
    for offset in range(1, n + 1):
        ty, tm = _months_back(y, m, offset)
        tp = f"{ty:04d}{tm:02d}"
        row = session.execute(
            text(
                "SELECT summary FROM reconciliation_run "
                "WHERE gstin_profile_id = :g AND period = :p "
                "  AND status = 'completed' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"g": str(gstin_profile_id), "p": tp},
        ).mappings().first()
        if row:
            summaries.append(dict(row["summary"]))
    return summaries


def _supplier_risk_paise(
    session: Session,
    gstin_profile_id,
    period: str,
    summary: dict,
) -> tuple[int, int]:
    """A supplier is 'risky' if it appears in the current period's
    supplier_default list OR in 2+ of the trailing 3 periods (chronic
    defaulter pattern). The union of both sets drives the paise tally.
    """
    def _top_sup_gstins(s: dict) -> set[str]:
        return {
            e.get("supplier_gstin", "")
            for e in s.get("supplier_default", {}).get("top_suppliers", [])
            if e.get("supplier_gstin")
        }

    # Current period — always risky.
    risky_gstins: set[str] = _top_sup_gstins(summary)

    # Trailing 3 periods: count how many periods each supplier appeared in.
    trailing_summaries = _trailing_recon_summaries(session, gstin_profile_id, period)
    appearance: dict[str, int] = {}
    for ts in trailing_summaries:
        for gstin in _top_sup_gstins(ts):
            appearance[gstin] = appearance.get(gstin, 0) + 1

    # Chronic = defaulted in 2+ of the last 3 periods.
    chronic = {g for g, count in appearance.items() if count >= 2}
    risky_gstins |= chronic
    y, m = int(period[:4]), int(period[4:])
    total = int(
        session.execute(
            text(
                "SELECT COALESCE(sum(total_paise), 0) FROM invoice "
                "WHERE gstin_profile_id = :g "
                "  AND direction = 'purchase' "
                "  AND status = 'active' "
                "  AND counterparty_gstin IS NOT NULL "
                "  AND EXTRACT(YEAR FROM invoice_date) = :y "
                "  AND EXTRACT(MONTH FROM invoice_date) = :m"
            ),
            {"g": str(gstin_profile_id), "y": y, "m": m},
        ).scalar()
        or 0
    )
    if not risky_gstins:
        return 0, total
    risky = int(
        session.execute(
            text(
                "SELECT COALESCE(sum(total_paise), 0) FROM invoice "
                "WHERE gstin_profile_id = :g "
                "  AND direction = 'purchase' "
                "  AND status = 'active' "
                "  AND counterparty_gstin = ANY(:sup) "
                "  AND EXTRACT(YEAR FROM invoice_date) = :y "
                "  AND EXTRACT(MONTH FROM invoice_date) = :m"
            ),
            {
                "g": str(gstin_profile_id),
                "y": y,
                "m": m,
                "sup": list(risky_gstins),
            },
        ).scalar()
        or 0
    )
    return risky, total


def _persist_snapshot(
    firm_id: uuid.UUID | str,
    gstin_profile_id: uuid.UUID | str,
    return_type: str,
    period: str,
    result: ScoreResult,
) -> uuid.UUID:
    """Append a row to ``readiness_snapshot``. Never updates; every call
    is a new immutable row (append-only)."""
    blockers_json = [b.__dict__ for b in result.blockers]
    with firm_scoped_session(firm_id) as session:
        row = session.execute(
            text(
                """
                INSERT INTO readiness_snapshot (
                    firm_id, gstin_profile_id, return_type, period,
                    score, blockers, arithmetic, rule_pack_version
                ) VALUES (
                    :fid, :gid, CAST(:rt AS return_type), :p,
                    :s, CAST(:b AS JSONB), CAST(:a AS JSONB), :v
                )
                RETURNING id
                """
            ),
            {
                "fid": str(firm_id),
                "gid": str(gstin_profile_id),
                "rt": return_type,
                "p": period,
                "s": result.score,
                "b": json.dumps(blockers_json),
                "a": json.dumps(result.arithmetic),
                "v": result.arithmetic.get("rule_pack_version"),
            },
        )
        return row.scalar_one()
