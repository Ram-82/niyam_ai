"""/scheduler/reminders — cron-only trigger for the due-date reminder sweep.

Auth is X-Scheduler-Token (never a user JWT — the sweep runs across
firms and must be inaccessible to any human account).
"""
from __future__ import annotations

import hmac
import logging
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import text

from app.config import settings
from app.db import owner_engine
from app.reminders import sweep_reminders


logger = logging.getLogger(__name__)


router = APIRouter(tags=["scheduler"])


# Different key from the GSP sweep so the two crons don't block each
# other. Value chosen at random; only needs to be stable across process
# restarts.
_REMINDERS_LOCK_KEY = 8_240_726_2


def _require_scheduler_token(
    x_scheduler_token: Optional[str] = Header(
        default=None, alias="X-Scheduler-Token"
    ),
) -> str:
    """Same discipline as the GSP scheduler: empty env = 503; wrong
    token = 401; constant-time compare so a leaked prefix isn't a timing
    oracle."""
    expected = settings.gsp_scheduler_token or ""
    if not expected:
        raise HTTPException(status_code=503, detail="scheduler_disabled")
    presented = x_scheduler_token or ""
    if not hmac.compare_digest(expected, presented):
        raise HTTPException(status_code=401, detail="invalid_scheduler_token")
    return presented


@router.post("/scheduler/reminders/sweep")
def reminders_sweep(
    _token: str = Depends(_require_scheduler_token),
    today: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> dict:
    """Fire the due-date reminder sweep for ``today`` (or now, UTC).

    Concurrency: guarded by a Postgres advisory lock so overlapping
    cron fires cannot double-dispatch. If the lock is held we log +
    return skipped rather than block.
    """
    day: date = (
        date.fromisoformat(today) if today else datetime.now(tz=timezone.utc).date()
    )

    with owner_engine.begin() as conn:
        got_lock = conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"),
            {"k": _REMINDERS_LOCK_KEY},
        ).scalar_one()
    if not got_lock:
        logger.warning("reminders.scheduler.skipped_concurrency_locked today=%s", day)
        return {
            "today": day.isoformat(),
            "status": "skipped_concurrency_locked",
        }

    try:
        report = sweep_reminders(day)
    finally:
        with owner_engine.begin() as conn:
            conn.execute(
                text("SELECT pg_advisory_unlock(:k)"),
                {"k": _REMINDERS_LOCK_KEY},
            )

    return {
        "today": day.isoformat(),
        "status": "ok",
        "dispatched": report.dispatched,
        "skipped_filed": report.skipped_filed,
        "skipped_duplicate": report.skipped_duplicate,
        "skipped_no_due_date": report.skipped_no_due_date,
        "skipped_not_at_threshold": report.skipped_not_at_threshold,
        "firms_visited": report.firms_visited,
        "errors": report.errors,
    }
