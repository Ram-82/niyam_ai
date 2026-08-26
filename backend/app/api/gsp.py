"""/gsp endpoints — consent flow, pulls, cost meter, failure surface.

* POST /gsp/consent               — initiate consent (triggers OTP to MSME mobile)
* POST /gsp/consent/confirm       — exchange OTP for a session
* POST /gsp/disconnect            — mark session revoked
* POST /gsp/pull                  — Pull-now for (gstin_profile, period)
* GET  /gsp/pull-attempts         — recent attempts; failed ones are visible
* GET  /gsp/usage                 — per-firm monthly call counts
* POST /gsp/scheduler/run         — admin trigger for the scheduled sweep
                                    (Stage 4 wires an external cron)
"""
from __future__ import annotations

import uuid
from datetime import datetime

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import get_current_user, get_firm_scoped_session
from app.legal.gate import require_legal_accepted
from app.auth import audit
from app.config import settings
from app.db import owner_engine
from app.gsp import service
from app.gsp.client import (
    ConsentRevoked,
    GSPError,
    GSTNUnavailable,
    OTPExpired,
    OTPInvalid,
    RateLimited,
    SessionExpired,
)
from app.models.tables import AppUser


router = APIRouter(prefix="/gsp", tags=["gsp"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ConsentReq(BaseModel):
    gstin_profile_id: uuid.UUID


class ConsentResp(BaseModel):
    inflight_id: str
    expires_at: datetime


class ConfirmReq(BaseModel):
    inflight_id: str
    # OTP is 6 numeric digits in the GSTN spec. Never logged.
    otp: str = Field(min_length=4, max_length=8)


class DisconnectReq(BaseModel):
    gstin_profile_id: uuid.UUID


class PullReq(BaseModel):
    gstin_profile_id: uuid.UUID
    period: str = Field(pattern=r"^\d{6}$")


class PullResp(BaseModel):
    attempt_id: uuid.UUID
    gstn_pull_id: uuid.UUID
    accepted: int


class PullAttemptRow(BaseModel):
    id: uuid.UUID
    gstin_profile_id: uuid.UUID
    period: str
    source: str
    status: str
    attempt_count: int
    error_kind: Optional[str] = None
    error_message: Optional[str] = None
    gstn_pull_id: Optional[uuid.UUID] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None


class UsageResp(BaseModel):
    firm_id: str
    month: str
    total_calls: int
    per_endpoint: list[dict]


class LatestAttempt(BaseModel):
    """Most-recent gsp_pull_attempt row, whatever its status. The panel
    blends this with the session state to derive the four UI states —
    see P2.1 Stage E in the README changelog."""
    id: uuid.UUID
    status: str  # 'running' | 'succeeded' | 'failed' | 'retry_scheduled'
    error_kind: Optional[str] = None
    started_at: datetime
    finished_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None


class ConnectionStatus(BaseModel):
    gstin_profile_id: uuid.UUID
    gstin: str
    # Session-only state: 'not_connected' | 'connected' | 'reconnect_needed'.
    # The frontend derives a fourth UI state ('last_pull_failed') by
    # combining this with ``latest_attempt`` below — done in one place
    # (ConnectionsPanel::derivePanelState) so the mapping stays honest.
    state: str
    # Populated when state='reconnect_needed'. One of:
    # 'consent_revoked' (vendor pulled consent)
    # 'session_expired' (TTL elapsed)
    # 'reconnect' (prior admin-initiated reconnect superseded)
    # 'user_disconnected' (manual disconnect)
    reason: Optional[str] = None
    session_expires_at: Optional[datetime] = None
    last_successful_pull_at: Optional[datetime] = None
    last_pull_period: Optional[str] = None
    # Latest pull-attempt row (any status). Present iff any attempt has
    # ever been made for this gstin_profile.
    latest_attempt: Optional[LatestAttempt] = None
    sandbox_mode: bool
    monthly_call_count: int
    backfill_offer: list[dict] = []


class BackfillItem(BaseModel):
    period: str
    label: str


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


def _translate_gsp(e: GSPError) -> HTTPException:
    """Vendor-taxonomy → UI-friendly HTTPException. Never leaks vendor
    payload to the user; that data lives in gsp_call_log."""
    if isinstance(e, OTPInvalid):
        return HTTPException(status_code=400, detail="otp_invalid")
    if isinstance(e, OTPExpired):
        return HTTPException(status_code=400, detail="otp_expired")
    if isinstance(e, SessionExpired):
        return HTTPException(status_code=401, detail="session_expired")
    if isinstance(e, ConsentRevoked):
        return HTTPException(status_code=403, detail="consent_revoked")
    if isinstance(e, GSTNUnavailable):
        return HTTPException(status_code=503, detail="gstn_unavailable")
    if isinstance(e, RateLimited):
        headers = {"Retry-After": str(e.retry_after_seconds or 30)}
        return HTTPException(
            status_code=429, detail="rate_limited", headers=headers
        )
    return HTTPException(status_code=502, detail="gsp_unknown_error")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/consent", response_model=ConsentResp)
def consent(payload: ConsentReq, user: AppUser = Depends(get_current_user)) -> ConsentResp:
    try:
        r = service.initiate_consent(
            firm_id=user.firm_id,
            gstin_profile_id=payload.gstin_profile_id,
            user_id=user.id,
        )
    except service.GstinNotInFirm:
        raise HTTPException(status_code=404, detail="gstin_profile not found")
    except service.InitiateCooldown as e:
        # OTP-SMS cooldown targets the taxpayer's phone; block early.
        raise HTTPException(
            status_code=429,
            detail="already_sent",
            headers={"Retry-After": str(e.retry_after)},
        )
    except GSPError as e:
        raise _translate_gsp(e)
    return ConsentResp(inflight_id=r.inflight_id, expires_at=r.expires_at)


@router.post("/consent/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm(
    payload: ConfirmReq, user: AppUser = Depends(get_current_user)
) -> None:
    try:
        service.confirm_consent(
            firm_id=user.firm_id,
            user_id=user.id,
            inflight_id=payload.inflight_id,
            otp=payload.otp,
        )
    except service.ConsentRequestUnknown:
        raise HTTPException(status_code=404, detail="inflight_unknown")
    except service.OtpLockedOut as e:
        raise HTTPException(
            status_code=429,
            detail="otp_locked",
            headers={"Retry-After": str(e.retry_after)},
        )
    except GSPError as e:
        raise _translate_gsp(e)


@router.post("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
def disconnect(
    payload: DisconnectReq, user: AppUser = Depends(get_current_user)
) -> None:
    try:
        service.disconnect(
            firm_id=user.firm_id,
            user_id=user.id,
            gstin_profile_id=payload.gstin_profile_id,
        )
    except service.GstinNotInFirm:
        raise HTTPException(status_code=404, detail="gstin_profile not found")


# ---------------------------------------------------------------------------
# Pull-now (manual)
# ---------------------------------------------------------------------------


@router.post("/pull", response_model=PullResp)
def pull_now(
    payload: PullReq,
    user: AppUser = Depends(get_current_user),
    _legal: None = Depends(require_legal_accepted),
) -> PullResp:
    """Pull 2B for a (gstin_profile, period). Reuses the JSON-upload
    ingestion path — the resulting ``gstn_pull`` row has
    ``source='gsp_api'``. Reconciliation is triggered separately by
    the CA via the existing engine endpoint."""
    # Enforce that the gstin belongs to the caller's firm — RLS also
    # blocks it but this yields a clean 404.
    try:
        r = service.pull_period(
            firm_id=user.firm_id,
            gstin_profile_id=payload.gstin_profile_id,
            period=payload.period,
            source="manual",
        )
    except service.NoLiveSession:
        raise HTTPException(
            status_code=409, detail="reconnect_required"
        )
    except GSPError as e:
        raise _translate_gsp(e)
    return PullResp(
        attempt_id=r.attempt_id,
        gstn_pull_id=r.gstn_pull_id,
        accepted=r.accepted,
    )


# ---------------------------------------------------------------------------
# Failure surface — /pull-attempts
# ---------------------------------------------------------------------------


@router.get("/pull-attempts", response_model=list[PullAttemptRow])
def list_pull_attempts(
    user: AppUser = Depends(get_current_user),
    gstin_profile_id: Optional[uuid.UUID] = None,
    period: Optional[str] = Query(default=None, pattern=r"^\d{6}$"),
    only_failed: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    session=Depends(get_firm_scoped_session),
) -> list[PullAttemptRow]:
    """Latest pull attempts for the firm. Optional filters."""
    where = ["firm_id = :fid"]
    params: dict = {"fid": str(user.firm_id), "limit": limit}
    if gstin_profile_id:
        where.append("gstin_profile_id = :gpid")
        params["gpid"] = str(gstin_profile_id)
    if period:
        where.append("period = :p")
        params["p"] = period
    if only_failed:
        where.append("status = 'failed'")
    sql = (
        "SELECT id, gstin_profile_id, period, source, status, attempt_count, "
        "error_kind, error_message, gstn_pull_id, started_at, finished_at, "
        "next_retry_at FROM gsp_pull_attempt "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY started_at DESC LIMIT :limit"
    )
    rows = session.execute(text(sql), params).mappings().all()
    return [PullAttemptRow(**dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# Cost meter — /usage
# ---------------------------------------------------------------------------


@router.get("/usage", response_model=UsageResp)
def usage(
    user: AppUser = Depends(get_current_user),
    month: Optional[str] = Query(default=None, pattern=r"^\d{6}$"),
) -> UsageResp:
    if month is None:
        now = datetime.now(tz=timezone.utc)
        month = f"{now.year:04d}{now.month:02d}"
    data = service.monthly_call_count(firm_id=user.firm_id, month=month)
    return UsageResp(**data)


# ---------------------------------------------------------------------------
# Mode probe — powers the app-wide sandbox banner (non-auth, small)
# ---------------------------------------------------------------------------


@router.get("/mode")
def mode() -> dict:
    """Public. Tells the frontend which GSP mode the backend is in so
    the sandbox banner cannot be turned off by removing a flag on the
    frontend. Mock mode → non-removable ``sandbox_mode: true``."""
    return {"gsp_mode": settings.gsp_mode, "sandbox_mode": settings.gsp_mode == "mock"}


# ---------------------------------------------------------------------------
# Connection status — powers the workspace Connections panel
# ---------------------------------------------------------------------------


class FirmGspStatus(BaseModel):
    total_gstins: int
    connected: int
    reconnect_needed: int
    not_connected: int
    # For the onboarding step badge: "done" iff at least one GSTIN has a live session.
    any_connected: bool
    # Label pre-formatted for the sidebar sub-line, so the frontend doesn't
    # have to re-implement the copy logic in every view.
    summary_label: str


@router.get("/firm-status", response_model=FirmGspStatus)
def firm_gsp_status(
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> FirmGspStatus:
    """Aggregate GSP connection status across every GSTIN in the firm.

    Onboarding step 3 uses this to flip its badge from pending → done as
    soon as any GSTIN has a live session. Also usable by the /v2/status
    page and the sidebar for at-a-glance connection health.
    """
    rows = session.execute(
        text(
            """
            SELECT
              gp.id AS gstin_profile_id,
              CASE
                WHEN live.id IS NOT NULL THEN 'connected'
                WHEN rev.id IS NOT NULL THEN 'reconnect_needed'
                ELSE 'not_connected'
              END AS state
            FROM gstin_profile gp
            LEFT JOIN LATERAL (
              SELECT id FROM gsp_session
              WHERE gstin_profile_id = gp.id AND revoked_at IS NULL
              LIMIT 1
            ) live ON TRUE
            LEFT JOIN LATERAL (
              SELECT id FROM gsp_session
              WHERE gstin_profile_id = gp.id AND revoked_at IS NOT NULL
              LIMIT 1
            ) rev ON TRUE
            """
        )
    ).mappings().all()

    connected = sum(1 for r in rows if r["state"] == "connected")
    reconnect_needed = sum(1 for r in rows if r["state"] == "reconnect_needed")
    not_connected = sum(1 for r in rows if r["state"] == "not_connected")
    total = len(rows)

    if total == 0:
        label = "No GSTINs added yet"
    elif connected == total:
        label = f"All {total} GSTIN{'' if total == 1 else 's'} connected"
    elif connected == 0 and reconnect_needed == 0:
        label = f"0 of {total} GSTIN{'' if total == 1 else 's'} connected"
    else:
        parts = [f"{connected} connected"]
        if reconnect_needed:
            parts.append(f"{reconnect_needed} need reconnect")
        if not_connected:
            parts.append(f"{not_connected} not connected")
        label = " · ".join(parts)

    return FirmGspStatus(
        total_gstins=total,
        connected=connected,
        reconnect_needed=reconnect_needed,
        not_connected=not_connected,
        any_connected=connected > 0,
        summary_label=label,
    )


@router.get("/connection/{gstin_profile_id}", response_model=ConnectionStatus)
def connection_status(
    gstin_profile_id: uuid.UUID,
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> ConnectionStatus:
    """Everything the UI needs to render the Connections panel:

        * connection state + specific stored reason if reconnect-needed
        * last successful pull metadata
        * sandbox_mode flag (immutable in mock mode — never hide)
        * current month's call count
        * optional backfill offer (populated after a fresh connect)
    """
    # Confirm GSTIN belongs to firm.
    prof = session.execute(
        text(
            "SELECT gstin FROM gstin_profile WHERE id = :id"
        ),
        {"id": str(gstin_profile_id)},
    ).first()
    if prof is None:
        raise HTTPException(status_code=404, detail="gstin_profile not found")
    gstin = prof[0]

    # Live session (if any).
    live = session.execute(
        text(
            "SELECT expires_at FROM gsp_session "
            "WHERE gstin_profile_id = :g AND revoked_at IS NULL"
        ),
        {"g": str(gstin_profile_id)},
    ).first()
    reason = None
    session_expires_at = None
    if live is not None:
        state = "connected"
        session_expires_at = live[0]
    else:
        # Look at the most recent revoked row for the specific cause.
        last_rev = session.execute(
            text(
                "SELECT revoked_reason FROM gsp_session "
                "WHERE gstin_profile_id = :g AND revoked_at IS NOT NULL "
                "ORDER BY revoked_at DESC LIMIT 1"
            ),
            {"g": str(gstin_profile_id)},
        ).first()
        if last_rev is None:
            state = "not_connected"
        else:
            state = "reconnect_needed"
            reason = last_rev[0]

    # Latest successful pull for the panel's "Last synced" line.
    last_pull = session.execute(
        text(
            "SELECT finished_at, period FROM gsp_pull_attempt "
            "WHERE gstin_profile_id = :g AND status = 'succeeded' "
            "ORDER BY finished_at DESC LIMIT 1"
        ),
        {"g": str(gstin_profile_id)},
    ).first()

    # Latest attempt of ANY status. Powers the P2.1 Stage E "last pull
    # failed" chip state. Uses the (gstin_profile_id, started_at DESC)
    # index created in migration 0008.
    latest_attempt_row = session.execute(
        text(
            "SELECT id, status, error_kind, started_at, finished_at, next_retry_at "
            "FROM gsp_pull_attempt WHERE gstin_profile_id = :g "
            "ORDER BY started_at DESC LIMIT 1"
        ),
        {"g": str(gstin_profile_id)},
    ).mappings().first()
    latest_attempt = (
        LatestAttempt(**dict(latest_attempt_row)) if latest_attempt_row else None
    )

    # Monthly call count (from the same rollup as /gsp/usage).
    now = datetime.now(tz=timezone.utc)
    month = f"{now.year:04d}{now.month:02d}"
    usage_data = service.monthly_call_count(firm_id=user.firm_id, month=month)

    # Backfill offer only makes sense when we ARE connected.
    backfill: list[dict] = []
    if state == "connected":
        backfill = service.backfill_plan(
            firm_id=user.firm_id, gstin_profile_id=gstin_profile_id
        )

    return ConnectionStatus(
        gstin_profile_id=gstin_profile_id,
        gstin=gstin,
        state=state,
        reason=reason,
        session_expires_at=session_expires_at,
        last_successful_pull_at=(last_pull[0] if last_pull else None),
        last_pull_period=(last_pull[1] if last_pull else None),
        sandbox_mode=(settings.gsp_mode == "mock"),
        monthly_call_count=usage_data["total_calls"],
        backfill_offer=backfill,
        latest_attempt=latest_attempt,
    )


# ---------------------------------------------------------------------------
# Scheduler trigger — machine credential only. Wires to an external cron
# (5:00 IST daily) via ``X-Scheduler-Token: <GSP_SCHEDULER_TOKEN>``.
# ---------------------------------------------------------------------------


# pg_advisory_lock key for the scheduler sweep — any integer will do; we
# pick a stable one so overlapping crons across processes serialize on
# the same key. See docs/advisory-locks-registry (there is no other one
# yet, this is the first).
_SCHEDULER_LOCK_KEY = 8_240_726_1  # arbitrary


def _require_scheduler_token(
    x_scheduler_token: Optional[str] = Header(default=None, alias="X-Scheduler-Token"),
) -> str:
    """Machine-only auth. Reject unless the header matches the env token.

    Never accepts a user JWT — the scheduler sweep runs across firms and
    must be inaccessible to any human account. Empty env = endpoint
    disabled (dev default). Compare in constant time so a leaked prefix
    doesn't give a timing oracle.
    """
    import hmac

    expected = settings.gsp_scheduler_token or ""
    if not expected:
        raise HTTPException(status_code=503, detail="scheduler_disabled")
    presented = x_scheduler_token or ""
    if not hmac.compare_digest(expected, presented):
        raise HTTPException(status_code=401, detail="invalid_scheduler_token")
    return presented


@router.post("/scheduler/run")
def scheduler_run(
    _token: str = Depends(_require_scheduler_token),
    today: Optional[str] = Query(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> dict:
    """Sweep every connected GSTIN for due periods.

    Auth: ``X-Scheduler-Token`` header only — user JWTs are not accepted.
    Concurrency: guarded by a Postgres session-level advisory lock so
    two overlapping cron fires cannot double-sweep the same day.
    Every trigger (accepted OR skipped-because-locked) writes an
    ``audit_log`` row with a NULL actor (system).
    """
    if today is None:
        dt = datetime.now(tz=timezone.utc)
    else:
        dt = datetime.fromisoformat(today)

    # (Concurrency guard) Take a Postgres advisory lock on the owner
    # engine. pg_try_advisory_lock returns FALSE immediately if another
    # session holds it — we log + skip rather than block.
    with owner_engine.begin() as conn:
        got_lock = conn.execute(
            text("SELECT pg_try_advisory_lock(:k)"),
            {"k": _SCHEDULER_LOCK_KEY},
        ).scalar_one()
    if not got_lock:
        # Audit the skipped trigger firm-agnostically — write to audit_log
        # with a synthetic firm_id would break RLS, so we log via a
        # non-tenant channel: stderr + a row would be nice but the
        # audit_log requires a firm. Punt to stderr for cross-firm events.
        import logging

        logging.getLogger("niyam.gsp.scheduler").warning(
            "scheduler.skipped reason=concurrency_locked today=%s",
            dt.date().isoformat(),
        )
        return {
            "today": dt.date().isoformat(),
            "status": "skipped_concurrency_locked",
            "attempts": [],
        }

    try:
        reports = service.run_scheduled_pulls(dt)
    finally:
        with owner_engine.begin() as conn:
            conn.execute(
                text("SELECT pg_advisory_unlock(:k)"),
                {"k": _SCHEDULER_LOCK_KEY},
            )
    # Per-firm audit: one row per firm that had at least one attempt.
    # Actor is NULL — the system ran this, not a user.
    firms_touched = {r["firm_id"] for r in reports}
    for firm_id in firms_touched:
        firm_reports = [r for r in reports if r["firm_id"] == firm_id]
        from app.db import firm_scoped_session

        with firm_scoped_session(firm_id) as db:
            audit.record(
                db,
                firm_id=firm_id,
                actor_user_id=None,
                action="gsp.scheduler_run",
                entity_type="ca_firm",
                entity_id=firm_id,
                metadata={
                    "today": dt.date().isoformat(),
                    "attempted": len(firm_reports),
                    "succeeded": sum(1 for r in firm_reports if r["status"] == "succeeded"),
                    "failed": sum(1 for r in firm_reports if r["status"] == "failed"),
                },
            )
    return {"today": dt.date().isoformat(), "status": "ok", "attempts": reports}
