"""WhatsApp delivery orchestration.

Two entry points map 1:1 to the API surface:

* :func:`send` — send a report OR chase against an approved
  ``delivery_request``. Same code path for both; the request row's
  ``purpose`` decides which template is used.
* :func:`apply_webhook_events` — Meta callback → delivery_attempt
  status update. No user context (webhook is machine-authed via HMAC).

Send flow:

    1. Gate: load + validate delivery_request (approved, unlocked, and
       — for chases — the near-miss review marker exists).
    2. Insert a ``delivery_attempt`` row with status='queued'.
    3. Call the transport. On success, UPDATE the attempt row to
       status='sent' + provider_message_id. On typed error, UPDATE with
       status='failed' + error_kind + error_message.
    4. Lock the delivery_request (set locked_at) so a subsequent send
       requires a fresh approval.
    5. Audit_log the outcome. Any subsequent webhook events update the
       existing attempt row.
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import text

from app.auth import audit
from app.config import settings
from app.db import firm_scoped_session, owner_engine
from app.whatsapp import gate as _gate
from app.whatsapp.transport_mock import get_singleton as _get_mock_singleton
from app.whatsapp.types import (
    ApprovalMissing,  # re-exported for callers that only import service
    DeliveryRequestLocked,
    DeliveryRequestUnknown,
    LANGUAGE_TO_TEMPLATE_LANG,
    NearMissReviewMissing,
    SendResult,
    Transport,
    WebhookStatusEvent,
    WhatsAppDisabled,
    WhatsAppError,
    WhatsAppErrorKind,
)


log = logging.getLogger("niyam.whatsapp.service")


# ---------------------------------------------------------------------------
# Adapter selection
# ---------------------------------------------------------------------------


def get_transport() -> Transport:
    """Return the transport for the current mode.

    Raises :class:`WhatsAppDisabled` when the feature flag is off, so the
    API layer surfaces a clean 503 without leaking which mode would run.
    """
    if not settings.whatsapp_enabled:
        raise WhatsAppDisabled(
            "whatsapp disabled (set WHATSAPP_ENABLED=1 to enable)"
        )
    if settings.whatsapp_mode == "mock":
        return _get_mock_singleton()
    if settings.whatsapp_mode == "meta":
        from app.whatsapp.transport_meta import MetaTransport

        return MetaTransport(
            access_token=settings.whatsapp_access_token,
            phone_number_id=settings.whatsapp_phone_number_id,
        )
    raise WhatsAppError(
        f"unknown WHATSAPP_MODE={settings.whatsapp_mode!r} "
        f"(expected mock|meta)"
    )


# ---------------------------------------------------------------------------
# delivery_request helpers
# ---------------------------------------------------------------------------


def create_report_request(
    *,
    firm_id: str | uuid.UUID,
    user_id: str | uuid.UUID,
    narration_run_id: str | uuid.UUID,
    whatsapp_number: str,
    template_name: str,
    template_language: str,
) -> uuid.UUID:
    """Create an unapproved delivery_request for a report send.

    The CA still has to POST /whatsapp/delivery-requests/{id}/approve
    before send can run.
    """
    with firm_scoped_session(firm_id) as db:
        # Look up the narration_run's gstin + client so the request row
        # carries the tenancy columns needed for RLS + reporting.
        row = db.execute(
            text(
                """
                SELECT nr.gstin_profile_id, gp.client_id
                FROM narration_run nr
                JOIN gstin_profile gp ON gp.id = nr.gstin_profile_id
                WHERE nr.id = :id
                """
            ),
            {"id": str(narration_run_id)},
        ).first()
        if row is None:
            raise DeliveryRequestUnknown(
                f"narration_run {narration_run_id} not found"
            )
        gpid, cid = row
        req = db.execute(
            text(
                """
                INSERT INTO delivery_request (
                    firm_id, client_id, gstin_profile_id, purpose,
                    narration_run_id, whatsapp_number_snapshot,
                    template_name, template_language, created_by
                ) VALUES (
                    :fid, :cid, :gpid, 'report_send',
                    :nrid, :wn, :tn, :tl, :ub
                )
                RETURNING id
                """
            ),
            {
                "fid": str(firm_id),
                "cid": str(cid),
                "gpid": str(gpid),
                "nrid": str(narration_run_id),
                "wn": whatsapp_number,
                "tn": template_name,
                "tl": template_language,
                "ub": str(user_id),
            },
        )
        return req.scalar_one()


def create_chase_request(
    *,
    firm_id: str | uuid.UUID,
    user_id: str | uuid.UUID,
    match_result_id: str | uuid.UUID,
    whatsapp_number: str,
    template_name: str,
    template_language: str,
) -> uuid.UUID:
    """Create an unapproved delivery_request for a supplier chase.

    The referenced match_result must exist AND belong to the caller's
    firm (RLS blocks cross-firm; we still raise DeliveryRequestUnknown
    early for a clean 404 rather than a silent RLS-empty-result). The
    match_result's bucket is NOT enforced here — the whatsapp gate
    checks near_miss_reviewed_at at send time, which implies bucket=
    'supplier_default' (only that bucket exposes the mark-reviewed
    endpoint) and is the authoritative gate.
    """
    with firm_scoped_session(firm_id) as db:
        # match_result has no gstin_profile_id of its own — it is derived
        # from whichever side of the pair is set. supplier_default rows
        # ALWAYS have invoice_id set (they are register rows with no 2B
        # match), so the invoice → gstin_profile → client chain resolves.
        # Missing_entry rows come from the b2b_entry side; we cover both
        # via COALESCE so a future policy that chases missing entries
        # does not silently break here.
        row = db.execute(
            text(
                """
                SELECT
                    COALESCE(i.gstin_profile_id, be_gp.id) AS gstin_profile_id,
                    COALESCE(i_gp.client_id, be_gp.client_id) AS client_id,
                    mr.bucket::text AS bucket
                FROM match_result mr
                LEFT JOIN invoice i ON i.id = mr.invoice_id
                LEFT JOIN gstin_profile i_gp ON i_gp.id = i.gstin_profile_id
                LEFT JOIN b2b_entry be ON be.id = mr.b2b_entry_id
                LEFT JOIN gstn_pull be_p ON be_p.id = be.gstn_pull_id
                LEFT JOIN gstin_profile be_gp ON be_gp.id = be_p.gstin_profile_id
                WHERE mr.id = :id
                """
            ),
            {"id": str(match_result_id)},
        ).mappings().first()
        if row is None:
            raise DeliveryRequestUnknown(
                f"match_result {match_result_id} not found"
            )
        if row["bucket"] != "supplier_default":
            # A chase against a probable/matched row is a category error;
            # not silently accept then fail at gate time.
            raise DeliveryRequestUnknown(
                f"match_result {match_result_id} bucket={row['bucket']} — "
                f"only supplier_default rows are chase-eligible"
            )
        if row["gstin_profile_id"] is None or row["client_id"] is None:
            # Shouldn't happen — a supplier_default row must have an
            # invoice_id (register side). If we get here, something in
            # the reconciliation engine wrote a malformed row.
            raise DeliveryRequestUnknown(
                f"match_result {match_result_id} has no resolvable "
                f"gstin_profile/client — reconciliation invariant broken"
            )
        req = db.execute(
            text(
                """
                INSERT INTO delivery_request (
                    firm_id, client_id, gstin_profile_id, purpose,
                    match_result_id, whatsapp_number_snapshot,
                    template_name, template_language, created_by
                ) VALUES (
                    :fid, :cid, :gpid, 'supplier_chase',
                    :mrid, :wn, :tn, :tl, :ub
                )
                RETURNING id
                """
            ),
            {
                "fid": str(firm_id),
                "cid": str(row["client_id"]),
                "gpid": str(row["gstin_profile_id"]),
                "mrid": str(match_result_id),
                "wn": whatsapp_number,
                "tn": template_name,
                "tl": template_language,
                "ub": str(user_id),
            },
        )
        return req.scalar_one()


def approve(
    *,
    firm_id: str | uuid.UUID,
    user_id: str | uuid.UUID,
    delivery_request_id: str | uuid.UUID,
) -> None:
    """Set approved_at + approved_by on the request.

    Idempotent — approving an already-approved request updates the
    approved_by/approved_at (audit-safe: only allowed while unlocked).
    """
    with firm_scoped_session(firm_id) as db:
        result = db.execute(
            text(
                """
                UPDATE delivery_request
                SET approved_by = :ub, approved_at = now()
                WHERE id = :id AND locked_at IS NULL
                RETURNING id
                """
            ),
            {"id": str(delivery_request_id), "ub": str(user_id)},
        ).first()
        if result is None:
            # Either doesn't exist, wrong firm (RLS), or already locked.
            # Disambiguate for the caller.
            found = db.execute(
                text(
                    "SELECT locked_at FROM delivery_request WHERE id = :id"
                ),
                {"id": str(delivery_request_id)},
            ).first()
            if found is None:
                raise DeliveryRequestUnknown(str(delivery_request_id))
            if found[0] is not None:
                raise DeliveryRequestLocked(str(delivery_request_id))
            raise DeliveryRequestUnknown(str(delivery_request_id))
        audit.record(
            db,
            firm_id=firm_id,
            actor_user_id=user_id,
            action="delivery.approved",
            entity_type="delivery_request",
            entity_id=delivery_request_id,
            metadata={},
        )


# ---------------------------------------------------------------------------
# send + apply_webhook_events
# ---------------------------------------------------------------------------


def _open_attempt(
    firm_id: str | uuid.UUID,
    delivery_request_id: str | uuid.UUID,
    provider: str,
) -> uuid.UUID:
    with firm_scoped_session(firm_id) as db:
        row = db.execute(
            text(
                """
                INSERT INTO delivery_attempt (
                    firm_id, delivery_request_id, provider, status
                ) VALUES (
                    :fid, :drid, :prov, 'queued'
                )
                RETURNING id
                """
            ),
            {
                "fid": str(firm_id),
                "drid": str(delivery_request_id),
                "prov": provider,
            },
        )
        return row.scalar_one()


def _finish_attempt(
    firm_id: str | uuid.UUID,
    attempt_id: uuid.UUID,
    *,
    status: str,
    provider_message_id: Optional[str],
    error_kind: Optional[str],
    error_message: Optional[str],
) -> None:
    with firm_scoped_session(firm_id) as db:
        db.execute(
            text(
                """
                UPDATE delivery_attempt
                SET status = :st,
                    provider_message_id = :pmid,
                    error_kind = :ek,
                    error_message = :em,
                    failed_at = CASE WHEN :st = 'failed' THEN now() ELSE failed_at END
                WHERE id = :id
                """
            ),
            {
                "st": status,
                "pmid": provider_message_id,
                "ek": error_kind,
                "em": error_message,
                "id": str(attempt_id),
            },
        )


def _lock_request(firm_id: str | uuid.UUID, delivery_request_id: str | uuid.UUID) -> None:
    with firm_scoped_session(firm_id) as db:
        db.execute(
            text(
                "UPDATE delivery_request SET locked_at = now() "
                "WHERE id = :id AND locked_at IS NULL"
            ),
            {"id": str(delivery_request_id)},
        )


def send(
    *,
    firm_id: str | uuid.UUID,
    user_id: str | uuid.UUID,
    delivery_request_id: str | uuid.UUID,
    media_bytes: Optional[bytes] = None,
    media_mime: Optional[str] = "application/pdf",
) -> tuple[uuid.UUID, SendResult | None]:
    """Send the report / chase. Returns (attempt_id, send_result_or_None).

    Raises the gate + transport exceptions unchanged so the API layer
    can map them to typed HTTP responses. A failure still leaves a
    delivery_attempt row on the record — the audit story never has a
    silent send-that-wasn't.
    """
    transport = get_transport()  # may raise WhatsAppDisabled

    with firm_scoped_session(firm_id) as db:
        req = _gate.load_and_validate(
            db, firm_id=firm_id, delivery_request_id=delivery_request_id
        )

    attempt_id = _open_attempt(firm_id, delivery_request_id, transport.provider)

    try:
        result = transport.send_template(
            to_e164=req["whatsapp_number_snapshot"],
            template_name=req["template_name"],
            template_lang=req["template_language"],
            media_bytes=media_bytes,
            media_mime=media_mime,
        )
    except WhatsAppError as e:
        _finish_attempt(
            firm_id,
            attempt_id,
            status="failed",
            provider_message_id=None,
            error_kind=e.kind.value,
            error_message=str(e)[:500],
        )
        _lock_request(firm_id, delivery_request_id)
        with firm_scoped_session(firm_id) as db:
            audit.record(
                db,
                firm_id=firm_id,
                actor_user_id=user_id,
                action="delivery.failed",
                entity_type="delivery_request",
                entity_id=delivery_request_id,
                metadata={
                    "attempt_id": str(attempt_id),
                    "error_kind": e.kind.value,
                    "http_status": e.http_status,
                },
            )
        raise

    _finish_attempt(
        firm_id,
        attempt_id,
        status="sent",
        provider_message_id=result.provider_message_id,
        error_kind=None,
        error_message=None,
    )
    _lock_request(firm_id, delivery_request_id)
    with firm_scoped_session(firm_id) as db:
        audit.record(
            db,
            firm_id=firm_id,
            actor_user_id=user_id,
            action=(
                "report.sent" if req["purpose"] == "report_send"
                else "supplier_chase.sent"
            ),
            entity_type="delivery_request",
            entity_id=delivery_request_id,
            metadata={
                "attempt_id": str(attempt_id),
                "provider": transport.provider,
                "provider_message_id": result.provider_message_id,
            },
        )
    return attempt_id, result


# ---------------------------------------------------------------------------
# Webhook — machine-authed, no firm scope in the call itself. We resolve
# firm scope by looking up the delivery_attempt row by provider_message_id.
# ---------------------------------------------------------------------------


def apply_webhook_events(events: list[WebhookStatusEvent]) -> int:
    """Apply Meta status callbacks to matching delivery_attempt rows.

    Returns the number of rows updated. Unknown message ids (spam,
    stale ids from a wiped test DB) are ignored — Meta redelivers on
    5xx so we would rather no-op than 500 back.

    Runs owner-side because a webhook has no firm scope; the FROM
    (delivery_attempt) row's firm_id is authoritative for RLS anyway.
    """
    if not events:
        return 0
    updated = 0
    with owner_engine.begin() as conn:
        for ev in events:
            # Map Meta status → our status column. 'sent' from webhook is
            # a no-op if we already set 'sent' at send-time; still write
            # it to be idempotent.
            status_col_map = {
                "sent": ("status", None),
                "delivered": ("delivered_at", "delivered"),
                "read": ("read_at", "read"),
                "failed": ("failed_at", "failed"),
            }
            entry = status_col_map.get(ev.status)
            if entry is None:
                continue  # unknown status — ignore
            ts_col, new_status = entry

            if ts_col == "status":
                r = conn.execute(
                    text(
                        "UPDATE delivery_attempt "
                        "SET status = 'sent' "
                        "WHERE provider_message_id = :pmid "
                        "AND status = 'queued'"
                    ),
                    {"pmid": ev.provider_message_id},
                )
            else:
                if new_status == "failed":
                    r = conn.execute(
                        text(
                            f"UPDATE delivery_attempt "
                            f"SET status = :ns, {ts_col} = to_timestamp(:ts), "
                            f"    error_kind = :ek, error_message = :em "
                            f"WHERE provider_message_id = :pmid"
                        ),
                        {
                            "ns": new_status,
                            "ts": ev.at_epoch,
                            "pmid": ev.provider_message_id,
                            "ek": ev.error_kind,
                            "em": (ev.error_message or "")[:500] or None,
                        },
                    )
                else:
                    r = conn.execute(
                        text(
                            f"UPDATE delivery_attempt "
                            f"SET status = :ns, {ts_col} = to_timestamp(:ts) "
                            f"WHERE provider_message_id = :pmid "
                            f"AND status != 'failed'"
                            # never regress a failed row back to delivered/read
                        ),
                        {
                            "ns": new_status,
                            "ts": ev.at_epoch,
                            "pmid": ev.provider_message_id,
                        },
                    )
            updated += r.rowcount or 0
    return updated
