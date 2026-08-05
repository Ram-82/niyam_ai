"""WhatsApp service integration tests.

Exercise the full service.send flow against a real Postgres + the mock
transport. Covers:

* Feature flag off → WhatsAppDisabled.
* Missing approval → ApprovalMissing (no attempt row inserted).
* Approved report send → delivery_attempt row + audit_log +
  request locked.
* Send against locked request → DeliveryRequestLocked.
* Supplier chase without near-miss review → NearMissReviewMissing.
* Supplier chase WITH near-miss review → succeeds.
* Transport failure (rate limited) → delivery_attempt.status='failed'
  with error_kind + request still locks (an attempted send is still
  an attempt on record).
* Immutable columns on delivery_attempt guard against tampering.
* Webhook events promote status delivered → read; ignore unknown ids.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

from app.config import settings
from app.db import owner_engine
from app.whatsapp import service, webhook
from app.whatsapp.transport_mock import MockTransport, get_singleton
from app.whatsapp.types import (
    ApprovalMissing,
    DeliveryRequestLocked,
    DeliveryRequestUnknown,
    InvalidNumber,
    NearMissReviewMissing,
    RateLimited,
    WebhookStatusEvent,
    WhatsAppDisabled,
)


# ---------------------------------------------------------------------------
# Feature flag + fresh mock singleton per test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _enable_whatsapp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "whatsapp_enabled", True)
    monkeypatch.setattr(settings, "whatsapp_mode", "mock")
    # Reset the module-level mock singleton so send counters + sent list
    # start clean each test.
    mock = get_singleton()
    mock.sent.clear()
    mock.next_error = None
    # Restart the id counter so message_ids are deterministic per test.
    import itertools
    mock._counter = itertools.count(1)


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_gstin_and_narration(bootstrap: dict) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Create client + gstin + a stub narration_run row.

    Returns (client_id, gstin_profile_id, narration_run_id).
    """
    firm_id = bootstrap["firm_id"]
    client_id = uuid.uuid4()
    gstin_id = uuid.uuid4()
    pull_id = uuid.uuid4()
    period = "202607"
    with owner_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO client (id, firm_id, trade_name, whatsapp_number) "
                "VALUES (:cid, :fid, 'Beta Traders', :wn)"
            ),
            {"cid": client_id, "fid": firm_id, "wn": "+919876543210"},
        )
        conn.execute(
            text(
                "INSERT INTO gstin_profile (id, firm_id, client_id, gstin, state_code) "
                "VALUES (:gid, :fid, :cid, '29ABCDE1234F1Z5', '29')"
            ),
            {"gid": gstin_id, "fid": firm_id, "cid": client_id},
        )
        # A gstn_pull to hang reconciliation on (unused here, but avoids FK
        # pain if a future test adds a chase).
        conn.execute(
            text(
                """
                INSERT INTO gstn_pull (
                    id, firm_id, gstin_profile_id, return_type, period,
                    raw_payload, source
                ) VALUES (
                    :pid, :fid, :gid, 'GSTR2B', :p,
                    CAST('{}' AS JSONB), 'json_import'
                )
                """
            ),
            {"pid": pull_id, "fid": firm_id, "gid": gstin_id, "p": period},
        )
        nr_id = conn.execute(
            text(
                """
                INSERT INTO narration_run (
                    firm_id, gstin_profile_id, return_type, period,
                    language, provider, model, facts, output
                ) VALUES (
                    :fid, :gid, 'GSTR1', :p, 'en', 'mock', 'template-v1',
                    CAST('{"stub": true}' AS JSONB),
                    CAST('{"stub": true}' AS JSONB)
                )
                RETURNING id
                """
            ),
            {"fid": firm_id, "gid": gstin_id, "p": period},
        ).scalar_one()
    return client_id, gstin_id, nr_id


def _create_report_request(b: dict, nr_id: uuid.UUID) -> uuid.UUID:
    return service.create_report_request(
        firm_id=b["firm_id"],
        user_id=b["user_id"],
        narration_run_id=nr_id,
        whatsapp_number="+919876543210",
        template_name="niyam_report_v1",
        template_language="en_US",
    )


# ---------------------------------------------------------------------------
# Feature flag + gate paths
# ---------------------------------------------------------------------------


def test_feature_flag_off_raises_disabled(
    monkeypatch: pytest.MonkeyPatch, bootstrap_firm
) -> None:
    b = bootstrap_firm()
    _, _, nr_id = _seed_gstin_and_narration(b)
    req_id = _create_report_request(b, nr_id)
    service.approve(
        firm_id=b["firm_id"], user_id=b["user_id"], delivery_request_id=req_id
    )
    monkeypatch.setattr(settings, "whatsapp_enabled", False)
    with pytest.raises(WhatsAppDisabled):
        service.send(
            firm_id=b["firm_id"],
            user_id=b["user_id"],
            delivery_request_id=req_id,
        )


def test_send_without_approval_raises_and_writes_no_attempt(
    bootstrap_firm,
) -> None:
    b = bootstrap_firm()
    _, _, nr_id = _seed_gstin_and_narration(b)
    req_id = _create_report_request(b, nr_id)
    # No approve() call.
    with pytest.raises(ApprovalMissing):
        service.send(
            firm_id=b["firm_id"],
            user_id=b["user_id"],
            delivery_request_id=req_id,
        )
    # And no attempt row was created.
    with owner_engine.begin() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM delivery_attempt "
                "WHERE delivery_request_id = :id"
            ),
            {"id": str(req_id)},
        ).scalar_one()
    assert count == 0


def test_approve_then_send_persists_attempt_and_locks(bootstrap_firm) -> None:
    b = bootstrap_firm()
    _, _, nr_id = _seed_gstin_and_narration(b)
    req_id = _create_report_request(b, nr_id)
    service.approve(
        firm_id=b["firm_id"], user_id=b["user_id"], delivery_request_id=req_id
    )

    attempt_id, result = service.send(
        firm_id=b["firm_id"],
        user_id=b["user_id"],
        delivery_request_id=req_id,
        media_bytes=b"%PDF-fake",
    )
    assert result is not None
    assert result.provider == "mock"

    with owner_engine.begin() as conn:
        attempt = conn.execute(
            text(
                "SELECT status, provider, provider_message_id FROM delivery_attempt "
                "WHERE id = :id"
            ),
            {"id": str(attempt_id)},
        ).mappings().first()
    assert attempt["status"] == "sent"
    assert attempt["provider"] == "mock"
    assert attempt["provider_message_id"] == "wamid.mock.000001"

    # Request is now locked.
    with owner_engine.begin() as conn:
        locked = conn.execute(
            text("SELECT locked_at FROM delivery_request WHERE id = :id"),
            {"id": str(req_id)},
        ).scalar_one()
    assert locked is not None

    # audit_log carries report.sent.
    with owner_engine.begin() as conn:
        actions = [
            r[0]
            for r in conn.execute(
                text("SELECT action FROM audit_log WHERE firm_id = :fid ORDER BY at"),
                {"fid": str(b["firm_id"])},
            ).all()
        ]
    assert "delivery.approved" in actions
    assert "report.sent" in actions


def test_send_against_locked_request_raises(bootstrap_firm) -> None:
    b = bootstrap_firm()
    _, _, nr_id = _seed_gstin_and_narration(b)
    req_id = _create_report_request(b, nr_id)
    service.approve(
        firm_id=b["firm_id"], user_id=b["user_id"], delivery_request_id=req_id
    )
    service.send(
        firm_id=b["firm_id"], user_id=b["user_id"], delivery_request_id=req_id
    )
    with pytest.raises(DeliveryRequestLocked):
        service.send(
            firm_id=b["firm_id"],
            user_id=b["user_id"],
            delivery_request_id=req_id,
        )


# ---------------------------------------------------------------------------
# Transport failure path
# ---------------------------------------------------------------------------


def test_transport_rate_limited_marks_attempt_failed_and_locks(
    bootstrap_firm,
) -> None:
    b = bootstrap_firm()
    _, _, nr_id = _seed_gstin_and_narration(b)
    req_id = _create_report_request(b, nr_id)
    service.approve(
        firm_id=b["firm_id"], user_id=b["user_id"], delivery_request_id=req_id
    )
    mock = get_singleton()
    mock.next_error = RateLimited(
        "throttled", http_status=429, retry_after_seconds=30
    )
    with pytest.raises(RateLimited):
        service.send(
            firm_id=b["firm_id"],
            user_id=b["user_id"],
            delivery_request_id=req_id,
        )
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT status, error_kind, failed_at FROM delivery_attempt "
                "WHERE delivery_request_id = :id"
            ),
            {"id": str(req_id)},
        ).mappings().first()
    assert row["status"] == "failed"
    assert row["error_kind"] == "rate_limited"
    assert row["failed_at"] is not None
    # Failed send still locks — audit says "we tried once".
    with owner_engine.begin() as conn:
        locked = conn.execute(
            text("SELECT locked_at FROM delivery_request WHERE id = :id"),
            {"id": str(req_id)},
        ).scalar_one()
    assert locked is not None


# ---------------------------------------------------------------------------
# Supplier chase near-miss gate
# ---------------------------------------------------------------------------


def _seed_supplier_chase_request(
    b: dict, *, near_miss_reviewed: bool
) -> uuid.UUID:
    """Seed a supplier_chase delivery_request pointing at a match_result.

    ``near_miss_reviewed=True`` writes context.near_miss_reviewed_at so
    the gate passes; False leaves it unset so the gate raises.
    """
    firm_id = b["firm_id"]
    client_id, gstin_id, _ = _seed_gstin_and_narration(b)
    with owner_engine.begin() as conn:
        # Need a reconciliation_run + match_result to point at.
        pull_id = conn.execute(
            text(
                """
                INSERT INTO gstn_pull (
                    firm_id, gstin_profile_id, return_type, period,
                    raw_payload, source
                ) VALUES (
                    :fid, :gid, 'GSTR2B', '202607',
                    CAST('{}' AS JSONB), 'json_import'
                )
                RETURNING id
                """
            ),
            {"fid": firm_id, "gid": gstin_id},
        ).scalar_one()
        run_id = conn.execute(
            text(
                """
                INSERT INTO reconciliation_run (
                    firm_id, gstin_profile_id, period, rule_pack_version,
                    gstn_pull_id, summary
                ) VALUES (
                    :fid, :gid, '202607', '1.0.0', :pid, CAST('{}' AS JSONB)
                )
                RETURNING id
                """
            ),
            {"fid": firm_id, "gid": gstin_id, "pid": pull_id},
        ).scalar_one()
        context_json = (
            {"near_miss_reviewed_at": "2026-08-01T10:00:00Z"}
            if near_miss_reviewed
            else {}
        )
        mr_id = conn.execute(
            text(
                """
                INSERT INTO match_result (
                    firm_id, gstin_profile_id, reconciliation_run_id,
                    bucket, context
                ) VALUES (
                    :fid, :gid, :rid, 'supplier_default', CAST(:ctx AS JSONB)
                )
                RETURNING id
                """
            ),
            {
                "fid": firm_id,
                "gid": gstin_id,
                "rid": run_id,
                "ctx": json.dumps(context_json),
            },
        ).scalar_one()
        req_id = conn.execute(
            text(
                """
                INSERT INTO delivery_request (
                    firm_id, client_id, gstin_profile_id, purpose,
                    match_result_id, whatsapp_number_snapshot,
                    template_name, template_language, created_by,
                    approved_by, approved_at
                ) VALUES (
                    :fid, :cid, :gid, 'supplier_chase',
                    :mrid, '+919876543210',
                    'niyam_supplier_chase_v1', 'en_US', :ub,
                    :ub, now()
                )
                RETURNING id
                """
            ),
            {
                "fid": firm_id,
                "cid": client_id,
                "gid": gstin_id,
                "mrid": mr_id,
                "ub": b["user_id"],
            },
        ).scalar_one()
    return req_id


def test_supplier_chase_without_near_miss_review_raises(
    bootstrap_firm,
) -> None:
    b = bootstrap_firm()
    req_id = _seed_supplier_chase_request(b, near_miss_reviewed=False)
    with pytest.raises(NearMissReviewMissing):
        service.send(
            firm_id=b["firm_id"],
            user_id=b["user_id"],
            delivery_request_id=req_id,
        )


def test_supplier_chase_with_near_miss_review_succeeds(bootstrap_firm) -> None:
    b = bootstrap_firm()
    req_id = _seed_supplier_chase_request(b, near_miss_reviewed=True)
    _, result = service.send(
        firm_id=b["firm_id"],
        user_id=b["user_id"],
        delivery_request_id=req_id,
    )
    assert result is not None
    # audit action for a chase is different from a report.
    with owner_engine.begin() as conn:
        actions = [
            r[0]
            for r in conn.execute(
                text("SELECT action FROM audit_log WHERE firm_id = :fid ORDER BY at"),
                {"fid": str(b["firm_id"])},
            ).all()
        ]
    assert "supplier_chase.sent" in actions


# ---------------------------------------------------------------------------
# delivery_attempt immutability + no delete
# ---------------------------------------------------------------------------


def test_delivery_attempt_immutable_fields_reject_mutation(bootstrap_firm) -> None:
    b = bootstrap_firm()
    _, _, nr_id = _seed_gstin_and_narration(b)
    req_id = _create_report_request(b, nr_id)
    service.approve(
        firm_id=b["firm_id"], user_id=b["user_id"], delivery_request_id=req_id
    )
    attempt_id, _ = service.send(
        firm_id=b["firm_id"], user_id=b["user_id"], delivery_request_id=req_id
    )
    with owner_engine.begin() as conn:
        with pytest.raises(Exception, match="immutable columns"):
            conn.execute(
                text("UPDATE delivery_attempt SET provider = 'meta' WHERE id = :id"),
                {"id": str(attempt_id)},
            )
    with owner_engine.begin() as conn:
        with pytest.raises(Exception, match="append-only"):
            conn.execute(
                text("DELETE FROM delivery_attempt WHERE id = :id"),
                {"id": str(attempt_id)},
            )


# ---------------------------------------------------------------------------
# Webhook events end-to-end
# ---------------------------------------------------------------------------


def test_webhook_events_promote_status_and_ignore_unknown(bootstrap_firm) -> None:
    b = bootstrap_firm()
    _, _, nr_id = _seed_gstin_and_narration(b)
    req_id = _create_report_request(b, nr_id)
    service.approve(
        firm_id=b["firm_id"], user_id=b["user_id"], delivery_request_id=req_id
    )
    _, result = service.send(
        firm_id=b["firm_id"], user_id=b["user_id"], delivery_request_id=req_id
    )

    events = [
        WebhookStatusEvent(
            provider_message_id=result.provider_message_id,
            status="delivered",
            at_epoch=1_700_000_000,
        ),
        WebhookStatusEvent(
            provider_message_id=result.provider_message_id,
            status="read",
            at_epoch=1_700_000_060,
        ),
        WebhookStatusEvent(
            provider_message_id="wamid.unknown.999",
            status="delivered",
            at_epoch=1_700_000_000,
        ),
    ]
    updated = service.apply_webhook_events(events)
    # Two of three matched (delivered, read).
    assert updated == 2

    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT status, delivered_at, read_at FROM delivery_attempt "
                "WHERE provider_message_id = :pmid"
            ),
            {"pmid": result.provider_message_id},
        ).mappings().first()
    assert row["status"] == "read"
    assert row["delivered_at"] is not None
    assert row["read_at"] is not None


def test_webhook_failed_does_not_regress_after_read(bootstrap_firm) -> None:
    """If Meta sends 'failed' after we already recorded a 'read', the
    'failed' branch is applied but a subsequent 'delivered' or 'read'
    must NOT overwrite the failed status (regression guard)."""
    b = bootstrap_firm()
    _, _, nr_id = _seed_gstin_and_narration(b)
    req_id = _create_report_request(b, nr_id)
    service.approve(
        firm_id=b["firm_id"], user_id=b["user_id"], delivery_request_id=req_id
    )
    _, result = service.send(
        firm_id=b["firm_id"], user_id=b["user_id"], delivery_request_id=req_id
    )
    # Mark failed via webhook.
    service.apply_webhook_events(
        [
            WebhookStatusEvent(
                provider_message_id=result.provider_message_id,
                status="failed",
                at_epoch=1_700_000_000,
                error_kind="131047",
                error_message="Re-engagement",
            )
        ]
    )
    # Now a stale 'delivered' arrives — must be ignored.
    service.apply_webhook_events(
        [
            WebhookStatusEvent(
                provider_message_id=result.provider_message_id,
                status="delivered",
                at_epoch=1_700_000_060,
            )
        ]
    )
    with owner_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT status, failed_at, error_kind FROM delivery_attempt "
                "WHERE provider_message_id = :pmid"
            ),
            {"pmid": result.provider_message_id},
        ).mappings().first()
    assert row["status"] == "failed"
    assert row["error_kind"] == "131047"
