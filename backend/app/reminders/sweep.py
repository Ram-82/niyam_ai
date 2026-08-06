"""Reminder sweep — cross-firm nudge dispatch.

Called by ``POST /scheduler/reminders/sweep`` on a cron schedule. Given
a wall-clock date, walks every firm's active GSTINs, computes the
GSTR-1 / GSTR-3B due date for the current and prior period, and for
each configured "days-before-due" threshold that matches, dispatches
a nudge email to every recipient assigned to that GSTIN's client.

Idempotency is the ``reminder_log`` UNIQUE constraint — the sweep
issues INSERT ... ON CONFLICT DO NOTHING and only dispatches when the
insert actually planted a row. Two concurrent sweeps for the same day
therefore cannot double-email a recipient.

The endpoint layer serialises full sweeps via a Postgres advisory
lock; this module is safe under concurrency too but the lock keeps
work from being duplicated.
"""
from __future__ import annotations

import logging
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import text

from app.config import settings
from app.db import firm_scoped_session, owner_engine
from app.email import send_due_date_reminder_email
from app.rules.pack import get_active_rule_pack


logger = logging.getLogger(__name__)


# Days-before-due thresholds we fire on. Signed so a future overdue-nudge
# phase can add negative entries (e.g. -1 = "1 day overdue"). Keep this
# short — every entry multiplies the fan-out by number-of-recipients.
REMINDER_THRESHOLDS_DAYS: tuple[int, ...] = (7, 3, 1, 0)

# Which return types we nudge. Order matters only for stable audit logs.
RETURN_TYPES: tuple[str, ...] = ("GSTR1", "GSTR3B")


@dataclass
class SweepReport:
    dispatched: int = 0
    skipped_filed: int = 0
    skipped_duplicate: int = 0
    skipped_no_due_date: int = 0
    skipped_not_at_threshold: int = 0
    firms_visited: int = 0
    errors: list[str] = field(default_factory=list)


def _compute_due_date(
    pack_due_dates: dict, return_type: str, scheme: str, period: str
) -> Optional[date]:
    """Same shape as engines/scoring/service._due_date — kept local so
    the sweep does not import a scoring internal."""
    day = (pack_due_dates.get(return_type) or {}).get(scheme)
    if day is None:
        return None
    year, month = int(period[:4]), int(period[4:])
    if month == 12:
        y, m = year + 1, 1
    else:
        y, m = year, month + 1
    day = min(int(day), monthrange(y, m)[1])
    return date(y, m, day)


def _candidate_periods(today: date) -> list[str]:
    """Periods that could conceivably have a due-date within [today, today+7d].

    Only the immediately-prior period is typically in-window (its return
    is due mid-following-month). Include the previous two prior periods
    as a safety margin against calendar-edge cases.
    """
    def _prev(y: int, m: int, n: int) -> tuple[int, int]:
        m -= n
        while m < 1:
            m += 12
            y -= 1
        return y, m

    out = []
    for n in (0, 1, 2):
        y, m = _prev(today.year, today.month, n)
        out.append(f"{y:04d}{m:02d}")
    return out


def _load_firm_ids() -> list[str]:
    """Firms that have opted IN to the reminder sweep.

    A per-firm ``reminders_enabled`` flag (default true) lets an admin
    silence the nudges for their firm without touching the global
    settings.reminders_enabled kill switch.
    """
    with owner_engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id FROM ca_firm WHERE reminders_enabled = TRUE")
        ).fetchall()
    return [str(r[0]) for r in rows]


def _load_recipients_for_gid(session, gid_id: str, client_id: str) -> list[dict]:
    """Return the users who should be nudged for this GID.

    Active firm admins are always included; staff must be assigned to the
    client via ``client_assignment``. Inactive users are skipped. Users
    with no TOTP confirmed are still nudged — the reminder is a heads-up,
    not an action that requires an account state.
    """
    rows = session.execute(
        text(
            """
            SELECT DISTINCT au.id::text AS user_id, au.email AS email
            FROM app_user au
            LEFT JOIN client_assignment ca
              ON ca.user_id = au.id AND ca.client_id = :client_id
            WHERE au.is_active = TRUE
              AND (au.role = 'admin' OR ca.user_id IS NOT NULL)
            """
        ),
        {"client_id": client_id},
    ).mappings().all()
    return [dict(r) for r in rows]


def _filing_run_status(session, gid_id: str, period: str, return_type: str) -> Optional[str]:
    row = session.execute(
        text(
            """
            SELECT status::text
            FROM filing_run
            WHERE gstin_profile_id = :g
              AND period = :p
              AND return_type = :r
            """
        ),
        {"g": gid_id, "p": period, "r": return_type},
    ).first()
    return row[0] if row else None


def sweep_reminders(today: Optional[date] = None) -> SweepReport:
    """Dispatch all due-date reminders for ``today``.

    Silently no-op — but still returns a fresh report — when
    ``settings.reminders_enabled`` is False. That lets an operator wire
    the cron before the feature launches; the endpoint returns 202 and
    the report shows dispatched=0 in the audit trail.
    """
    report = SweepReport()
    if not settings.reminders_enabled:
        logger.info("reminders.sweep.disabled")
        return report

    day = today or datetime.now(tz=timezone.utc).date()
    pack = get_active_rule_pack()
    due_cfg = (pack.payload.get("scoring", {}) or {}).get("due_dates", {}) or {}

    firm_ids = _load_firm_ids()
    for firm_id in firm_ids:
        report.firms_visited += 1
        try:
            _sweep_one_firm(firm_id, day, due_cfg, report)
        except Exception as exc:
            # Never let one firm's failure block the others.
            logger.exception("reminders.sweep.firm_failed", extra={"firm_id": firm_id})
            report.errors.append(f"{firm_id}: {exc}")

    logger.info(
        "reminders.sweep.done",
        extra={
            "dispatched": report.dispatched,
            "skipped_filed": report.skipped_filed,
            "skipped_duplicate": report.skipped_duplicate,
            "firms_visited": report.firms_visited,
            "errors": len(report.errors),
        },
    )
    return report


def _sweep_one_firm(
    firm_id: str, day: date, due_cfg: dict, report: SweepReport
) -> None:
    with firm_scoped_session(firm_id) as session:
        gids = session.execute(
            text(
                """
                SELECT id::text AS gid, client_id::text AS client_id,
                       gstin, scheme::text AS scheme,
                       (SELECT trade_name FROM client c WHERE c.id = gp.client_id)
                           AS client_trade_name
                FROM gstin_profile gp
                """
            )
        ).mappings().all()

        for gid in gids:
            for return_type in RETURN_TYPES:
                for period in _candidate_periods(day):
                    _maybe_dispatch(
                        session=session,
                        firm_id=firm_id,
                        gid=dict(gid),
                        return_type=return_type,
                        period=period,
                        day=day,
                        due_cfg=due_cfg,
                        report=report,
                    )


def _maybe_dispatch(
    *,
    session,
    firm_id: str,
    gid: dict,
    return_type: str,
    period: str,
    day: date,
    due_cfg: dict,
    report: SweepReport,
) -> None:
    due = _compute_due_date(due_cfg, return_type, gid["scheme"], period)
    if due is None:
        report.skipped_no_due_date += 1
        return
    days_out = (due - day).days
    if days_out not in REMINDER_THRESHOLDS_DAYS:
        report.skipped_not_at_threshold += 1
        return
    status = _filing_run_status(session, gid["gid"], period, return_type)
    if status == "filed":
        report.skipped_filed += 1
        return

    recipients = _load_recipients_for_gid(session, gid["gid"], gid["client_id"])
    for r in recipients:
        _dispatch_one(
            session=session,
            firm_id=firm_id,
            gid_id=gid["gid"],
            gstin=gid["gstin"],
            client_trade_name=gid["client_trade_name"] or "",
            return_type=return_type,
            period=period,
            days_before_due=days_out,
            due_date=due,
            recipient_user_id=r["user_id"],
            recipient_email=str(r["email"]),
            report=report,
        )


def _dispatch_one(
    *,
    session,
    firm_id: str,
    gid_id: str,
    gstin: str,
    client_trade_name: str,
    return_type: str,
    period: str,
    days_before_due: int,
    due_date: date,
    recipient_user_id: str,
    recipient_email: str,
    report: SweepReport,
) -> None:
    """Insert the idempotency row; only dispatch on rowcount == 1."""
    result = session.execute(
        text(
            """
            INSERT INTO reminder_log (
                firm_id, gstin_profile_id, period, return_type,
                days_before_due, channel, recipient_user_id, recipient_email
            ) VALUES (
                :firm_id, :gid, :period, :return_type,
                :days, 'email', :ruid, :email
            )
            ON CONFLICT ON CONSTRAINT reminder_log_idempotency DO NOTHING
            """
        ),
        {
            "firm_id": firm_id,
            "gid": gid_id,
            "period": period,
            "return_type": return_type,
            "days": days_before_due,
            "ruid": recipient_user_id,
            "email": recipient_email,
        },
    )
    if result.rowcount == 0:
        report.skipped_duplicate += 1
        return

    try:
        send_due_date_reminder_email(
            to=recipient_email,
            gstin=gstin,
            client_trade_name=client_trade_name,
            return_type=return_type,
            period=period,
            due_date=due_date,
            days_before_due=days_before_due,
        )
    except Exception as exc:
        # The idempotency row is already committed — deliberate. Losing
        # sent_at just means we won't retry this recipient (spam-safety
        # bias). Operator can clear the row manually if they want a
        # retry, and the failure is logged loudly.
        logger.warning(
            "reminders.dispatch.email_failed",
            extra={
                "firm_id": firm_id,
                "gid_id": gid_id,
                "recipient_user_id": recipient_user_id,
                "error": str(exc),
            },
        )
        return

    session.execute(
        text(
            """
            UPDATE reminder_log
            SET sent_at = now()
            WHERE gstin_profile_id = :gid
              AND period = :period
              AND return_type = :return_type
              AND days_before_due = :days
              AND channel = 'email'
              AND recipient_user_id = :ruid
            """
        ),
        {
            "gid": gid_id,
            "period": period,
            "return_type": return_type,
            "days": days_before_due,
            "ruid": recipient_user_id,
        },
    )
    report.dispatched += 1
