"""GSP consent + session orchestration.

This is the vendor-neutral layer above :mod:`app.gsp.client`. It owns:

* Encryption of session tokens (via :mod:`app.gsp.crypto`) before they
  hit the DB. Plaintext tokens NEVER leave this module.
* Consent_log rows on every consent grant / revoke.
* Audit_log rows on connect / reconnect / disconnect (actor recorded).
* Per-``(user, gstin)`` lockout on OTP failures.
* Mapping vendor errors to :class:`GSPErrorKind` for the API + UI.

None of the surface here — arguments, returns, side effects — knows
about mock vs live. Wiring the current adapter is via
:func:`get_adapter` which reads ``settings.gsp_mode`` +
``settings.gsp_base_url``.

Server-side CONSENT_REVOKED mid-lifecycle
-----------------------------------------
When a pull raises :class:`ConsentRevoked` we:

    * Mark the live ``gsp_session`` row ``revoked_at = now()``, and set
      ``revoked_reason = 'consent_revoked'``.
    * Append a superseding ``consent_log`` row with ``revoked_at``
      populated so the paper trail matches P1's append-only convention.
    * Emit ``audit_log`` action ``gsp.consent_revoked`` (actor = system
      user, i.e. NULL — no human clicked this).
    * The UI now shows the GSTIN as "reconnect needed" — the CA
      re-runs the connect flow, a fresh live row is inserted, and
      the old revoked row remains for history.

The same treatment applies to :class:`SessionExpired` (revoked_reason
= 'session_expired') so we never silently drop a scheduled pull.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.auth import audit
from app.config import settings
from app.db import firm_scoped_session
from app.gsp import crypto, lockout, retry
from app.gsp.adapter_mock import MockGSPAdapter
from app.gsp.client import (
    ConsentRequest,
    ConsentRevoked,
    GSPClient,
    GSPError,
    GSPErrorKind,
    OTPExpired,
    OTPInvalid,
    RateLimited,
    Session,
    SessionExpired,
)
from app.ingestion.gstr2b_parser import parse_gstr2b_json
from app.ingestion.writer import bulk_insert_b2b_entries, insert_gstn_pull


# ---------------------------------------------------------------------------
# Adapter factory
# ---------------------------------------------------------------------------


def get_adapter() -> GSPClient:
    """Return the adapter for the current ``GSP_MODE``.

    Only 'mock' is wired today. Adding a real vendor is a single elif
    branch — see README §Swapping in a real GSP vendor.
    """
    if settings.gsp_mode == "mock":
        return MockGSPAdapter(base_url=settings.gsp_base_url)
    raise RuntimeError(
        f"GSP_MODE={settings.gsp_mode!r} has no adapter wired. "
        "Add one in app/gsp/service.py::get_adapter."
    )


# ---------------------------------------------------------------------------
# Errors surfaced to the API layer
# ---------------------------------------------------------------------------


class GstinNotInFirm(Exception):
    """The gstin_profile_id does not belong to the caller's firm.
    RLS will also block the write, but we detect early for a clear 404."""


class ConsentRequestUnknown(Exception):
    """No active in-flight consent request for the passed request_id."""


class OtpLockedOut(Exception):
    def __init__(self, retry_after: int) -> None:
        super().__init__("gsp otp temporarily locked")
        self.retry_after = retry_after


class InitiateCooldown(Exception):
    """Per-GSTIN OTP-SMS cooldown active. Blocks flooding the taxpayer's phone."""

    def __init__(self, retry_after: int) -> None:
        super().__init__("gsp initiate cooldown")
        self.retry_after = retry_after


# ---------------------------------------------------------------------------
# In-memory consent request cache (process-scoped).
#
# The vendor's request_id is opaque to the caller — we redirect the
# UI to pass a Niyam-generated id so we can bind (user, gstin) and
# retrieve the vendor context without trusting the client to
# round-trip anything. On confirm, we pull the vendor request_id
# from this cache. This is intentionally NOT persisted: the window
# is small (OTP TTL ~5 min) and losing it just makes the CA re-issue
# consent — no data at risk.
#
# OTPs are NEVER stored here or anywhere else.
# ---------------------------------------------------------------------------


@dataclass
class _InFlight:
    firm_id: str
    gstin_profile_id: str
    gstin: str
    user_id: str
    vendor_request_id: str
    created_at: float


_inflight: dict[str, _InFlight] = {}
_INFLIGHT_TTL = 15 * 60  # 15 min — well past the OTP window


def _gc_inflight() -> None:
    cutoff = time.time() - _INFLIGHT_TTL
    for k in list(_inflight.keys()):
        if _inflight[k].created_at < cutoff:
            _inflight.pop(k, None)


# ---------------------------------------------------------------------------
# GSTIN lookup
# ---------------------------------------------------------------------------


def _load_gstin(
    session: OrmSession, firm_id: str | uuid.UUID, gstin_profile_id: str | uuid.UUID
) -> str:
    row = session.execute(
        text(
            "SELECT gstin FROM gstin_profile "
            "WHERE id = :gid AND firm_id = :fid"
        ),
        {"gid": str(gstin_profile_id), "fid": str(firm_id)},
    ).first()
    if row is None:
        raise GstinNotInFirm(str(gstin_profile_id))
    return row[0]


# ---------------------------------------------------------------------------
# Call meter
# ---------------------------------------------------------------------------


def _log_call(
    session: OrmSession,
    firm_id: str | uuid.UUID,
    gstin_profile_id: Optional[str | uuid.UUID],
    endpoint: str,
    period: Optional[str],
    succeeded: bool,
    http_status: Optional[int],
    error_kind: Optional[str],
    started_at: float,
) -> None:
    session.execute(
        text(
            """
            INSERT INTO gsp_call_log (
                firm_id, gstin_profile_id, endpoint, period,
                succeeded, http_status, error_kind, latency_ms
            ) VALUES (
                :firm_id, :gpid, :ep, :pd,
                :ok, :hs, :ek, :ms
            )
            """
        ),
        {
            "firm_id": str(firm_id),
            "gpid": str(gstin_profile_id) if gstin_profile_id else None,
            "ep": endpoint,
            "pd": period,
            "ok": succeeded,
            "hs": http_status,
            "ek": error_kind,
            "ms": int((time.time() - started_at) * 1000),
        },
    )


# ---------------------------------------------------------------------------
# Consent flow
# ---------------------------------------------------------------------------


@dataclass
class InitiatedConsent:
    """What the API returns to the UI after /gsp/consent."""

    inflight_id: str
    expires_at: datetime


def initiate_consent(
    *,
    firm_id: str | uuid.UUID,
    gstin_profile_id: str | uuid.UUID,
    user_id: str | uuid.UUID,
) -> InitiatedConsent:
    """Ask the GSP to trigger an OTP against the GSTIN's registered mobile.

    Rate-limited per GSTIN — see :func:`app.gsp.lockout.try_reserve_initiate`.
    The cooldown targets the taxpayer's mobile phone (SMS flooding vector),
    which is why the key is the GSTIN itself, not the calling user.
    """
    _gc_inflight()
    adapter = get_adapter()
    started = time.time()

    # (1) Look up the GSTIN in its own tx (commits on exit).
    with firm_scoped_session(firm_id) as db:
        gstin = _load_gstin(db, firm_id, gstin_profile_id)

    # (2) Pre-flight the SMS-flood cooldown. Log the block in its own tx
    # so the raise below does not roll back the audit row.
    reserved, retry_after = lockout.try_reserve_initiate(gstin)
    if not reserved:
        with firm_scoped_session(firm_id) as db:
            _log_call(
                db,
                firm_id,
                gstin_profile_id,
                endpoint="consent",
                period=None,
                succeeded=False,
                http_status=None,
                error_kind="initiate_cooldown",
                started_at=started,
            )
        raise InitiateCooldown(retry_after=retry_after)

    # (3) Vendor call. Capture the outcome, write the call log in its own
    # tx, THEN raise outside the `with` so a failure log is never rolled
    # back by the propagating exception.
    consent_req: ConsentRequest | None = None
    vendor_error: GSPError | None = None
    try:
        consent_req = adapter.initiate_consent(gstin)
    except GSPError as e:
        vendor_error = e
    with firm_scoped_session(firm_id) as db:
        _log_call(
            db,
            firm_id,
            gstin_profile_id,
            endpoint="consent",
            period=None,
            succeeded=vendor_error is None,
            http_status=(vendor_error.http_status if vendor_error else 200),
            error_kind=(vendor_error.kind.value if vendor_error else None),
            started_at=started,
        )
    if vendor_error is not None:
        raise vendor_error

    inflight_id = uuid.uuid4().hex
    _inflight[inflight_id] = _InFlight(
        firm_id=str(firm_id),
        gstin_profile_id=str(gstin_profile_id),
        gstin=gstin,
        user_id=str(user_id),
        vendor_request_id=consent_req.request_id,
        created_at=time.time(),
    )
    return InitiatedConsent(inflight_id=inflight_id, expires_at=consent_req.expires_at)


def confirm_consent(
    *,
    firm_id: str | uuid.UUID,
    user_id: str | uuid.UUID,
    inflight_id: str,
    otp: str,
) -> None:
    """Exchange an OTP for a session, encrypt + store, write consent_log + audit_log.

    Raises OtpLockedOut if the ``(user, gstin)`` pair is currently locked
    out. Records lockout transitions to ``audit_log`` with
    ``action='gsp.otp_lockout'``. The OTP value itself is NEVER included
    in the audit metadata, logs, or exception messages.
    """
    inflight = _inflight.get(inflight_id)
    if inflight is None:
        raise ConsentRequestUnknown(inflight_id)
    if str(inflight.firm_id) != str(firm_id) or str(inflight.user_id) != str(user_id):
        # Different user or a firm-swapped session — treat as unknown.
        raise ConsentRequestUnknown(inflight_id)

    user_key = str(user_id)
    if lockout.is_locked(user_key, inflight.gstin):
        raise OtpLockedOut(retry_after=max(1, lockout.ttl_seconds(user_key, inflight.gstin)))

    adapter = get_adapter()
    consent_req = ConsentRequest(
        gstin=inflight.gstin,
        request_id=inflight.vendor_request_id,
        expires_at=datetime.utcnow(),
    )
    started = time.time()
    try:
        session = adapter.confirm_consent(consent_req, otp)
    except (OTPInvalid, OTPExpired) as e:
        # Record failure + audit lockout transition. NEVER log the OTP.
        with firm_scoped_session(firm_id) as db:
            _log_call(
                db,
                firm_id,
                inflight.gstin_profile_id,
                endpoint="confirm",
                period=None,
                succeeded=False,
                http_status=e.http_status,
                error_kind=e.kind.value,
                started_at=started,
            )
            count = lockout.record_failure(user_key, inflight.gstin)
            if count >= lockout.MAX_ATTEMPTS:
                # Audit the transition, not the OTP. Metadata carries the
                # kind only — no code, no OTP value.
                audit.record(
                    db,
                    firm_id=firm_id,
                    actor_user_id=user_id,
                    action="gsp.otp_lockout",
                    entity_type="gstin_profile",
                    entity_id=inflight.gstin_profile_id,
                    metadata={
                        "gstin": inflight.gstin,
                        "reason": "max_failed_attempts",
                    },
                )
        raise
    except RateLimited as e:
        with firm_scoped_session(firm_id) as db:
            _log_call(
                db,
                firm_id,
                inflight.gstin_profile_id,
                endpoint="confirm",
                period=None,
                succeeded=False,
                http_status=e.http_status,
                error_kind=e.kind.value,
                started_at=started,
            )
        raise
    except GSPError as e:
        with firm_scoped_session(firm_id) as db:
            _log_call(
                db,
                firm_id,
                inflight.gstin_profile_id,
                endpoint="confirm",
                period=None,
                succeeded=False,
                http_status=e.http_status,
                error_kind=e.kind.value,
                started_at=started,
            )
        raise

    # Success: clear counter, encrypt + persist.
    lockout.clear(user_key, inflight.gstin)
    ciphertext, key_version = crypto.encrypt(session.token)

    is_reconnect = False
    with firm_scoped_session(firm_id) as db:
        _log_call(
            db,
            firm_id,
            inflight.gstin_profile_id,
            endpoint="confirm",
            period=None,
            succeeded=True,
            http_status=200,
            error_kind=None,
            started_at=started,
        )
        # Any prior live row → revoked (this is a reconnect).
        existing = db.execute(
            text(
                "SELECT id FROM gsp_session "
                "WHERE gstin_profile_id = :gpid AND revoked_at IS NULL"
            ),
            {"gpid": inflight.gstin_profile_id},
        ).first()
        if existing is not None:
            is_reconnect = True
            db.execute(
                text(
                    "UPDATE gsp_session SET revoked_at = now(), "
                    "revoked_reason = 'reconnect' WHERE id = :id"
                ),
                {"id": str(existing[0])},
            )
        db.execute(
            text(
                """
                INSERT INTO gsp_session (
                    firm_id, gstin_profile_id, token_ciphertext, key_version,
                    vendor_context, issued_at, expires_at, connected_by
                ) VALUES (
                    :fid, :gpid, :ct, :kv,
                    CAST(:vc AS JSONB), :ia, :ea, :ub
                )
                """
            ),
            {
                "fid": str(firm_id),
                "gpid": inflight.gstin_profile_id,
                "ct": ciphertext,
                "kv": key_version,
                "vc": json.dumps(session.vendor_context or {}),
                "ia": session.issued_at,
                "ea": session.expires_at,
                "ub": str(user_id),
            },
        )
        # Consent + audit — actor recorded.
        db.execute(
            text(
                """
                INSERT INTO consent_log (
                    firm_id, client_id, purpose, granted_at, granted_by, metadata
                )
                SELECT
                    gp.firm_id, gp.client_id, 'gsp.gstr2b',
                    now(), :ub, CAST(:md AS JSONB)
                FROM gstin_profile gp
                WHERE gp.id = :gpid
                """
            ),
            {
                "ub": str(user_id),
                "md": json.dumps(
                    {"gstin": inflight.gstin, "action": "connect"}
                ),
                "gpid": inflight.gstin_profile_id,
            },
        )
        audit.record(
            db,
            firm_id=firm_id,
            actor_user_id=user_id,
            action="gsp.reconnect" if is_reconnect else "gsp.connect",
            entity_type="gstin_profile",
            entity_id=inflight.gstin_profile_id,
            metadata={"gstin": inflight.gstin},
        )

    # Successful confirm → drop the inflight so an OTP replay is a miss.
    _inflight.pop(inflight_id, None)


def disconnect(
    *,
    firm_id: str | uuid.UUID,
    user_id: str | uuid.UUID,
    gstin_profile_id: str | uuid.UUID,
) -> None:
    """Manually disconnect a GSTIN. Marks all live rows revoked, writes
    consent_log (revoke), writes audit_log.
    """
    with firm_scoped_session(firm_id) as db:
        gstin_row = db.execute(
            text(
                "SELECT gstin, client_id FROM gstin_profile "
                "WHERE id = :gid AND firm_id = :fid"
            ),
            {"gid": str(gstin_profile_id), "fid": str(firm_id)},
        ).first()
        if gstin_row is None:
            raise GstinNotInFirm(str(gstin_profile_id))
        gstin, client_id = gstin_row
        db.execute(
            text(
                "UPDATE gsp_session SET revoked_at = now(), "
                "revoked_reason = 'user_disconnected' "
                "WHERE gstin_profile_id = :gpid AND revoked_at IS NULL"
            ),
            {"gpid": str(gstin_profile_id)},
        )
        # Consent log: append a superseding revoke row.
        db.execute(
            text(
                """
                INSERT INTO consent_log (
                    firm_id, client_id, purpose, granted_at, revoked_at,
                    granted_by, metadata
                ) VALUES (
                    :fid, :cid, 'gsp.gstr2b', now(), now(), :ub, CAST(:md AS JSONB)
                )
                """
            ),
            {
                "fid": str(firm_id),
                "cid": str(client_id),
                "ub": str(user_id),
                "md": json.dumps(
                    {"gstin": gstin, "action": "disconnect"}
                ),
            },
        )
        audit.record(
            db,
            firm_id=firm_id,
            actor_user_id=user_id,
            action="gsp.disconnect",
            entity_type="gstin_profile",
            entity_id=gstin_profile_id,
            metadata={"gstin": gstin},
        )


def mark_session_dead(
    *,
    firm_id: str | uuid.UUID,
    gstin_profile_id: str | uuid.UUID,
    reason: str,
) -> None:
    """Called from the pull path when the vendor tells us the session is
    dead (SESSION_EXPIRED, CONSENT_REVOKED). No actor — the system did
    this in response to a vendor signal, so audit_log actor is NULL.
    """
    with firm_scoped_session(firm_id) as db:
        db.execute(
            text(
                "UPDATE gsp_session SET revoked_at = now(), "
                "revoked_reason = :r "
                "WHERE gstin_profile_id = :gpid AND revoked_at IS NULL"
            ),
            {"gpid": str(gstin_profile_id), "r": reason},
        )
        # CONSENT_REVOKED is also a consent-level event: log it.
        if reason == "consent_revoked":
            db.execute(
                text(
                    """
                    INSERT INTO consent_log (
                        firm_id, client_id, purpose, granted_at, revoked_at,
                        granted_by, metadata
                    )
                    SELECT
                        gp.firm_id, gp.client_id, 'gsp.gstr2b',
                        now(), now(), NULL, CAST(:md AS JSONB)
                    FROM gstin_profile gp
                    WHERE gp.id = :gpid
                    """
                ),
                {
                    "gpid": str(gstin_profile_id),
                    "md": json.dumps(
                        {"action": "revoked_by_vendor", "reason": reason}
                    ),
                },
            )
        audit.record(
            db,
            firm_id=firm_id,
            actor_user_id=None,
            action=(
                "gsp.consent_revoked"
                if reason == "consent_revoked"
                else "gsp.session_expired"
            ),
            entity_type="gstin_profile",
            entity_id=gstin_profile_id,
            metadata={"reason": reason},
        )


# ---------------------------------------------------------------------------
# Session lookup for Stage 3 pull path
# ---------------------------------------------------------------------------


@dataclass
class LiveSession:
    session: Session
    row_id: uuid.UUID


def load_live_session(
    *, firm_id: str | uuid.UUID, gstin_profile_id: str | uuid.UUID
) -> Optional[LiveSession]:
    """Return a decrypted live session for the GSTIN, or None.

    Never returns a session past its stored ``expires_at``. The Stage 3
    pull path will call this, then either use the session or trigger
    ``refresh_or_reauth`` + a re-persist, or mark the session dead.
    """
    with firm_scoped_session(firm_id) as db:
        row = db.execute(
            text(
                """
                SELECT id, gstin_profile_id, token_ciphertext, key_version,
                       vendor_context, issued_at, expires_at
                FROM gsp_session
                WHERE gstin_profile_id = :gpid AND revoked_at IS NULL
                """
            ),
            {"gpid": str(gstin_profile_id)},
        ).mappings().first()
        if row is None:
            return None
        gstin = db.execute(
            text("SELECT gstin FROM gstin_profile WHERE id = :id"),
            {"id": str(gstin_profile_id)},
        ).scalar_one()
    if row["expires_at"] <= datetime.now(tz=timezone.utc):
        return None
    token = crypto.decrypt(row["token_ciphertext"], row["key_version"])
    sess = Session(
        gstin=gstin,
        token=token,
        # Strip tzinfo so downstream .is_expired matches datetime.utcnow.
        issued_at=row["issued_at"].replace(tzinfo=None) if row["issued_at"].tzinfo else row["issued_at"],
        expires_at=row["expires_at"].replace(tzinfo=None) if row["expires_at"].tzinfo else row["expires_at"],
        vendor_context=row["vendor_context"] or {},
    )
    return LiveSession(session=sess, row_id=row["id"])


# ---------------------------------------------------------------------------
# Pull path — the shared entry for scheduled + manual GSTR-2B pulls.
# ---------------------------------------------------------------------------


class NoLiveSession(Exception):
    """Live session missing or dead. Surfaced as 'reconnect needed' in UI."""


@dataclass
class PullResult:
    attempt_id: uuid.UUID
    gstn_pull_id: uuid.UUID
    period: str
    accepted: int


def _open_attempt(
    firm_id: str | uuid.UUID,
    gstin_profile_id: str | uuid.UUID,
    period: str,
    source: str,
) -> uuid.UUID:
    with firm_scoped_session(firm_id) as db:
        row = db.execute(
            text(
                """
                INSERT INTO gsp_pull_attempt (
                    firm_id, gstin_profile_id, period, source,
                    status, attempt_count
                ) VALUES (
                    :fid, :gpid, :p, :src, 'running', 1
                )
                RETURNING id
                """
            ),
            {
                "fid": str(firm_id),
                "gpid": str(gstin_profile_id),
                "p": period,
                "src": source,
            },
        )
        return row.scalar_one()


def _update_attempt(
    firm_id: str | uuid.UUID,
    attempt_id: uuid.UUID,
    **fields,
) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k} = :{k}" for k in fields)
    params = {"id": str(attempt_id), **{k: v for k, v in fields.items()}}
    with firm_scoped_session(firm_id) as db:
        db.execute(
            text(f"UPDATE gsp_pull_attempt SET {cols} WHERE id = :id"),
            params,
        )


def pull_period(
    *,
    firm_id: str | uuid.UUID,
    gstin_profile_id: str | uuid.UUID,
    period: str,
    source: str = "manual",
) -> PullResult:
    """Fetch 2B for a period, persist, and record a pull attempt row.

    Flow — engineered so a failure is loud and queryable:

        1. Open ``gsp_pull_attempt`` row (status=running).
        2. Load the live session; if missing/dead → attempt fails with
           ``error_kind='session_dead'``, session row marked dead, UI
           surfaces "reconnect needed".
        3. ``run_with_retry(fetch_gstr2b)`` with taxonomy-aware policy.
           Between attempts, the attempt row transitions to
           ``retry_scheduled`` with ``next_retry_at`` set — the UI sees
           an in-progress retry rather than a stale "running".
        4. On success: use the SAME writer as the JSON-upload path
           (``insert_gstn_pull(..., source='gsp_api')`` +
           ``bulk_insert_b2b_entries``). Reconciliation reruns are
           triggered by the caller (Stage 3 API) — this function is
           idempotent per-attempt.
        5. On any GSPError (retryable exhausted or non-retryable): attempt
           row → status='failed', error_kind + error_message populated.
    """
    if source not in ("manual", "scheduled"):
        raise ValueError(f"source must be 'manual'|'scheduled', got {source!r}")

    attempt_id = _open_attempt(firm_id, gstin_profile_id, period, source)

    # (2) Live session or bail loud.
    live = load_live_session(firm_id=firm_id, gstin_profile_id=gstin_profile_id)
    if live is None:
        _update_attempt(
            firm_id,
            attempt_id,
            status="failed",
            finished_at=datetime.now(tz=timezone.utc),
            error_kind="session_dead",
            error_message=(
                "No live GSP session for this GSTIN. Reconnect required."
            ),
        )
        raise NoLiveSession(str(gstin_profile_id))

    adapter = get_adapter()
    policy = retry.load_policy()
    started_overall = time.time()

    # Between-attempt bookkeeping so the attempt row never looks stale.
    def _mark_retry(attempt_no: int, err: GSPError, wait_seconds: int) -> None:
        now = datetime.now(tz=timezone.utc)
        _update_attempt(
            firm_id,
            attempt_id,
            status="retry_scheduled",
            attempt_count=attempt_no + 1,
            error_kind=err.kind.value,
            error_message=f"{err.kind.value}: waiting {wait_seconds}s before retry",
            next_retry_at=now + timedelta(seconds=wait_seconds),
        )

    def _call() -> dict[str, Any]:
        call_started = time.time()
        try:
            payload = adapter.fetch_gstr2b(live.session, live.session.gstin, period)
        except GSPError as e:
            with firm_scoped_session(firm_id) as db:
                _log_call(
                    db,
                    firm_id,
                    gstin_profile_id,
                    endpoint="gstr2b",
                    period=period,
                    succeeded=False,
                    http_status=e.http_status,
                    error_kind=e.kind.value,
                    started_at=call_started,
                )
            raise
        with firm_scoped_session(firm_id) as db:
            _log_call(
                db,
                firm_id,
                gstin_profile_id,
                endpoint="gstr2b",
                period=period,
                succeeded=True,
                http_status=200,
                error_kind=None,
                started_at=call_started,
            )
        return payload

    try:
        payload, attempts = retry.run_with_retry(
            _call, policy=policy, on_retry=_mark_retry
        )
    except (SessionExpired, ConsentRevoked) as e:
        reason = "consent_revoked" if isinstance(e, ConsentRevoked) else "session_expired"
        mark_session_dead(
            firm_id=firm_id,
            gstin_profile_id=gstin_profile_id,
            reason=reason,
        )
        _update_attempt(
            firm_id,
            attempt_id,
            status="failed",
            finished_at=datetime.now(tz=timezone.utc),
            error_kind=e.kind.value,
            error_message=(
                "Session revoked by GSTN — reconnect required."
                if isinstance(e, ConsentRevoked)
                else "Session expired — reconnect required."
            ),
        )
        raise
    except GSPError as e:
        _update_attempt(
            firm_id,
            attempt_id,
            status="failed",
            finished_at=datetime.now(tz=timezone.utc),
            error_kind=e.kind.value,
            error_message=f"{e.kind.value}: pull failed after retries",
        )
        raise

    # (4) Success — reuse the JSON-upload writer path exactly.
    pull_id = insert_gstn_pull(
        firm_id=firm_id,
        gstin_profile_id=gstin_profile_id,
        period=period,
        raw_payload=payload,
        source="gsp_api",
    )
    parse = parse_gstr2b_json(payload, gstn_pull_id=str(pull_id))
    accepted = bulk_insert_b2b_entries(
        firm_id=firm_id, gstn_pull_id=pull_id, entries=parse.entries
    )
    _update_attempt(
        firm_id,
        attempt_id,
        status="succeeded",
        finished_at=datetime.now(tz=timezone.utc),
        attempt_count=attempts,
        gstn_pull_id=str(pull_id),
        error_kind=None,
        error_message=None,
        next_retry_at=None,
    )
    return PullResult(
        attempt_id=attempt_id,
        gstn_pull_id=pull_id,
        period=period,
        accepted=accepted,
    )


# ---------------------------------------------------------------------------
# Monthly cost meter
# ---------------------------------------------------------------------------


def monthly_call_count(
    *, firm_id: str | uuid.UUID, month: str
) -> dict[str, Any]:
    """Return per-endpoint call totals for the firm in ``month`` (YYYYMM).

    GSPs bill per call. This is the source of truth for internal
    unit-economics reporting; Stage 4 exposes it in admin UI.
    """
    if len(month) != 6 or not month.isdigit():
        raise ValueError("month must be YYYYMM")
    year, mm = int(month[:4]), int(month[4:])
    with firm_scoped_session(firm_id) as db:
        rows = db.execute(
            text(
                """
                SELECT endpoint,
                       COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE succeeded) AS successes,
                       COUNT(*) FILTER (WHERE NOT succeeded) AS failures
                FROM gsp_call_log
                WHERE firm_id = :fid
                  AND EXTRACT(YEAR FROM at) = :y
                  AND EXTRACT(MONTH FROM at) = :m
                GROUP BY endpoint
                ORDER BY endpoint
                """
            ),
            {"fid": str(firm_id), "y": year, "m": mm},
        ).mappings().all()
    per_endpoint = [dict(r) for r in rows]
    return {
        "firm_id": str(firm_id),
        "month": month,
        "per_endpoint": per_endpoint,
        "total_calls": sum(r["total"] for r in per_endpoint),
    }


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


def _period_for(dt: datetime) -> str:
    return f"{dt.year:04d}{dt.month:02d}"


def _prev_period(period: str) -> str:
    """YYYYMM → previous month YYYYMM."""
    y, m = int(period[:4]), int(period[4:])
    if m == 1:
        return f"{y - 1:04d}12"
    return f"{y:04d}{m - 1:02d}"


def due_periods_for_today(today: datetime) -> list[str]:
    """Which periods have a 2B ready to fetch, per rule-pack cutoff?

    Simple policy for P2 stage 3: for each day-in-month past
    ``gsp.2b_generation_day``, the PREVIOUS month is due. Before that,
    nothing is due for the previous month yet (2B hasn't been
    generated). Callers pull for every "due" period they don't already
    have a succeeded attempt on.
    """
    from app.rules.pack import get_active_rule_pack

    pack = get_active_rule_pack()
    day = int((pack.payload.get("gsp") or {}).get("2b_generation_day", 14))
    if today.day >= day:
        return [_prev_period(_period_for(today))]
    return []


def find_gstins_due(
    today: datetime,
) -> list[tuple[uuid.UUID, uuid.UUID, str]]:
    """Return (firm_id, gstin_profile_id, period) triples that:

        * have a live gsp_session (i.e. connected),
        * fall inside a due period per :func:`due_periods_for_today`,
        * have no succeeded gsp_pull_attempt yet for that period.

    Runs owner-side because the scheduler is not tied to a request; it
    is called by an admin trigger (Stage 4 wires a cron externally).
    """
    periods = due_periods_for_today(today)
    if not periods:
        return []
    from sqlalchemy import bindparam

    from app.db import owner_engine

    out: list[tuple[uuid.UUID, uuid.UUID, str]] = []
    with owner_engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT gp.firm_id, gp.id AS gstin_profile_id
                FROM gstin_profile gp
                JOIN gsp_session gs
                  ON gs.gstin_profile_id = gp.id
                 AND gs.revoked_at IS NULL
                 AND gs.expires_at > now()
                """
            )
        ).all()
        for firm_id, gpid in rows:
            for period in periods:
                exists = conn.execute(
                    text(
                        "SELECT 1 FROM gsp_pull_attempt "
                        "WHERE gstin_profile_id = :g "
                        "  AND period = :p "
                        "  AND status = 'succeeded' LIMIT 1"
                    ),
                    {"g": str(gpid), "p": period},
                ).first()
                if exists is None:
                    out.append((firm_id, gpid, period))
    return out


def backfill_plan(
    *,
    firm_id: str | uuid.UUID,
    gstin_profile_id: str | uuid.UUID,
    today: datetime | None = None,
) -> list[dict[str, Any]]:
    """Which periods should the CA be offered to backfill after connecting?

    Returns the N most-recent already-generated 2B periods (per the
    ``gsp.2b_generation_day`` knob) for which we have no succeeded
    ``gsp_pull_attempt`` yet. Each entry is
    ``{period: 'YYYYMM', label: 'June 2026'}``. The UI shows a
    "Backfill last N periods" prompt after a successful connect and
    calls the standard Pull-now endpoint per period. That way there is
    ONE ingestion path, exercised the same way whether the pull is
    scheduled, manual, or backfill.
    """
    from app.rules.pack import get_active_rule_pack

    pack = get_active_rule_pack()
    gsp_cfg = pack.payload.get("gsp") or {}
    n = int(gsp_cfg.get("backfill_periods", 3))
    gen_day = int(gsp_cfg.get("2b_generation_day", 14))
    if n <= 0:
        return []

    if today is None:
        today = datetime.now(tz=timezone.utc)

    # The most recent period whose 2B is generated.
    if today.day >= gen_day:
        newest_gen = _prev_period(_period_for(today))
    else:
        # Not yet past this month's cutoff → newest generated period is 2 back.
        newest_gen = _prev_period(_prev_period(_period_for(today)))

    # Walk backwards N periods.
    periods: list[str] = []
    p = newest_gen
    for _ in range(n):
        periods.append(p)
        p = _prev_period(p)

    # Filter out ones already succeeded (do not offer redundant pulls).
    with firm_scoped_session(firm_id) as db:
        done = {
            r[0]
            for r in db.execute(
                text(
                    "SELECT period FROM gsp_pull_attempt "
                    "WHERE gstin_profile_id = :g "
                    "  AND period = ANY(:ps) "
                    "  AND status = 'succeeded'"
                ),
                {"g": str(gstin_profile_id), "ps": periods},
            ).all()
        }
    return [
        {"period": p, "label": _period_label(p)}
        for p in periods
        if p not in done
    ]


_MONTH_LABELS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _period_label(period: str) -> str:
    y, m = int(period[:4]), int(period[4:])
    return f"{_MONTH_LABELS[m - 1]} {y}"


def run_scheduled_pulls(today: datetime) -> list[dict[str, Any]]:
    """Iterate :func:`find_gstins_due` and call :func:`pull_period` for each.

    Returns a small report per attempt so an admin trigger can log the
    outcome. Never raises to the caller: failures live on their
    ``gsp_pull_attempt`` rows (loud + queryable).
    """
    reports: list[dict[str, Any]] = []
    for firm_id, gpid, period in find_gstins_due(today):
        try:
            r = pull_period(
                firm_id=firm_id,
                gstin_profile_id=gpid,
                period=period,
                source="scheduled",
            )
            reports.append(
                {
                    "firm_id": str(firm_id),
                    "gstin_profile_id": str(gpid),
                    "period": period,
                    "status": "succeeded",
                    "gstn_pull_id": str(r.gstn_pull_id),
                }
            )
        except NoLiveSession:
            reports.append(
                {
                    "firm_id": str(firm_id),
                    "gstin_profile_id": str(gpid),
                    "period": period,
                    "status": "failed",
                    "error": "session_dead",
                }
            )
        except GSPError as e:
            reports.append(
                {
                    "firm_id": str(firm_id),
                    "gstin_profile_id": str(gpid),
                    "period": period,
                    "status": "failed",
                    "error": e.kind.value,
                }
            )
    return reports
