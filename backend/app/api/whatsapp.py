"""/whatsapp endpoints — approve + send + webhook + list.

* POST /whatsapp/delivery-requests           — create an unapproved request for a report
* POST /whatsapp/delivery-requests/{id}/approve — CA approves
* POST /whatsapp/delivery-requests/{id}/send    — execute (gated)
* GET  /whatsapp/attempts                    — recent delivery attempts (list)
* POST /whatsapp/webhook                     — Meta callback (HMAC-verified)

The webhook is intentionally NOT user-authed — Meta signs it. Any other
request goes through the same JWT/RLS surface every other endpoint uses.
"""
from __future__ import annotations

import base64
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.deps import get_current_user, get_firm_scoped_session
from app.config import settings
from app.models.tables import AppUser
from app.whatsapp import service, webhook
from app.whatsapp.types import (
    ApprovalMissing,
    DeliveryRequestLocked,
    DeliveryRequestUnknown,
    LANGUAGE_TO_TEMPLATE_LANG,
    NearMissReviewMissing,
    RateLimited,
    WhatsAppDisabled,
    WhatsAppError,
    WhatsAppErrorKind,
    is_valid_e164,
)


router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class CreateReportRequestReq(BaseModel):
    narration_run_id: uuid.UUID
    whatsapp_number: str = Field(min_length=8, max_length=20)
    # UI-language, translated to Meta's tag downstream.
    language: str = Field(default="en", pattern=r"^(en|hi|kn|mr)$")
    template_name: Optional[str] = None  # defaults to settings.whatsapp_template_report_name


class CreateChaseRequestReq(BaseModel):
    match_result_id: uuid.UUID
    whatsapp_number: str = Field(min_length=8, max_length=20)
    language: str = Field(default="en", pattern=r"^(en|hi|kn|mr)$")
    template_name: Optional[str] = None  # defaults to settings.whatsapp_template_chase_name


class DeliveryRequestCreatedResp(BaseModel):
    delivery_request_id: uuid.UUID


class SendReq(BaseModel):
    # PDF bytes, base64. Optional — if omitted, the send goes through
    # without a media header (some templates are text-only).
    pdf_base64: Optional[str] = None


class SendResp(BaseModel):
    attempt_id: uuid.UUID
    provider: str
    provider_message_id: str
    status: str


class DeliveryAttemptRow(BaseModel):
    id: uuid.UUID
    delivery_request_id: uuid.UUID
    provider: str
    status: str
    provider_message_id: Optional[str] = None
    error_kind: Optional[str] = None
    error_message: Optional[str] = None
    attempted_at: datetime
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None


class ChasePreviewResp(BaseModel):
    """Powers the chase modal preview so the CA sees the exact prose
    the supplier will read before Approve & Send."""
    language: str
    template_name: str
    body: str
    supplier_name: Optional[str] = None
    supplier_gstin: str
    firm_name: str


# ---------------------------------------------------------------------------
# Endpoints — auth-gated
# ---------------------------------------------------------------------------


def _translate_whatsapp_error(e: WhatsAppError) -> HTTPException:
    if e.kind == WhatsAppErrorKind.TEMPLATE_NOT_APPROVED:
        return HTTPException(status_code=400, detail="template_not_approved")
    if e.kind == WhatsAppErrorKind.INVALID_NUMBER:
        return HTTPException(status_code=400, detail="invalid_number")
    if e.kind == WhatsAppErrorKind.RATE_LIMITED:
        headers = {}
        if isinstance(e, RateLimited) and e.retry_after_seconds:
            headers["Retry-After"] = str(e.retry_after_seconds)
        return HTTPException(
            status_code=429, detail="rate_limited", headers=headers or None
        )
    if e.kind == WhatsAppErrorKind.META_5XX:
        return HTTPException(status_code=502, detail="meta_upstream_error")
    return HTTPException(status_code=502, detail="whatsapp_unknown_error")


@router.post("/delivery-requests", response_model=DeliveryRequestCreatedResp)
def create_delivery_request(
    payload: CreateReportRequestReq,
    user: AppUser = Depends(get_current_user),
) -> DeliveryRequestCreatedResp:
    if not is_valid_e164(payload.whatsapp_number):
        raise HTTPException(status_code=400, detail="invalid_e164_number")
    template_name = payload.template_name or settings.whatsapp_template_report_name
    template_lang = LANGUAGE_TO_TEMPLATE_LANG.get(payload.language, "en_US")
    try:
        req_id = service.create_report_request(
            firm_id=user.firm_id,
            user_id=user.id,
            narration_run_id=payload.narration_run_id,
            whatsapp_number=payload.whatsapp_number,
            template_name=template_name,
            template_language=template_lang,
        )
    except DeliveryRequestUnknown:
        raise HTTPException(status_code=404, detail="narration_run_not_found")
    return DeliveryRequestCreatedResp(delivery_request_id=req_id)


@router.post("/delivery-requests/chase", response_model=DeliveryRequestCreatedResp)
def create_chase_request(
    payload: CreateChaseRequestReq,
    user: AppUser = Depends(get_current_user),
) -> DeliveryRequestCreatedResp:
    """Supplier-chase delivery_request. Points at a match_result rather
    than a narration_run. The near-miss review gate is enforced at
    /send time (not here) — creating a chase request against an
    unreviewed near-miss is allowed; the CA can prepare the draft and
    review the near-misses in either order. The send will 409 with
    ``near_miss_review_missing`` until both are done."""
    if not is_valid_e164(payload.whatsapp_number):
        raise HTTPException(status_code=400, detail="invalid_e164_number")
    template_name = payload.template_name or settings.whatsapp_template_chase_name
    template_lang = LANGUAGE_TO_TEMPLATE_LANG.get(payload.language, "en_US")
    try:
        req_id = service.create_chase_request(
            firm_id=user.firm_id,
            user_id=user.id,
            match_result_id=payload.match_result_id,
            whatsapp_number=payload.whatsapp_number,
            template_name=template_name,
            template_language=template_lang,
        )
    except DeliveryRequestUnknown as e:
        raise HTTPException(status_code=404, detail=str(e))
    return DeliveryRequestCreatedResp(delivery_request_id=req_id)


@router.post(
    "/delivery-requests/{delivery_request_id}/approve",
    status_code=status.HTTP_204_NO_CONTENT,
)
def approve_delivery_request(
    delivery_request_id: uuid.UUID,
    user: AppUser = Depends(get_current_user),
) -> None:
    try:
        service.approve(
            firm_id=user.firm_id,
            user_id=user.id,
            delivery_request_id=delivery_request_id,
        )
    except DeliveryRequestUnknown:
        raise HTTPException(status_code=404, detail="delivery_request_not_found")
    except DeliveryRequestLocked:
        raise HTTPException(status_code=409, detail="delivery_request_locked")


@router.post(
    "/delivery-requests/{delivery_request_id}/send",
    response_model=SendResp,
)
def send_delivery(
    delivery_request_id: uuid.UUID,
    payload: SendReq,
    user: AppUser = Depends(get_current_user),
) -> SendResp:
    pdf_bytes: Optional[bytes] = None
    if payload.pdf_base64:
        try:
            pdf_bytes = base64.b64decode(payload.pdf_base64, validate=True)
        except Exception:
            raise HTTPException(status_code=400, detail="invalid_pdf_base64")
    try:
        attempt_id, result = service.send(
            firm_id=user.firm_id,
            user_id=user.id,
            delivery_request_id=delivery_request_id,
            media_bytes=pdf_bytes,
        )
    except WhatsAppDisabled:
        raise HTTPException(status_code=503, detail="whatsapp_disabled")
    except DeliveryRequestUnknown:
        raise HTTPException(status_code=404, detail="delivery_request_not_found")
    except DeliveryRequestLocked:
        raise HTTPException(status_code=409, detail="delivery_request_locked")
    except ApprovalMissing:
        raise HTTPException(status_code=409, detail="approval_missing")
    except NearMissReviewMissing:
        raise HTTPException(status_code=409, detail="near_miss_review_missing")
    except WhatsAppError as e:
        raise _translate_whatsapp_error(e)
    assert result is not None  # send returns SendResult on success path
    return SendResp(
        attempt_id=attempt_id,
        provider=result.provider,
        provider_message_id=result.provider_message_id,
        status=result.status,
    )


@router.get("/preview/chase", response_model=ChasePreviewResp)
def preview_chase(
    match_result_id: uuid.UUID = Query(...),
    language: str = Query(default="en", pattern=r"^(en|hi|kn|mr)$"),
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
) -> ChasePreviewResp:
    """Render the chase body the supplier will read.

    No delivery_request is created — this is a pure preview. The CA
    sees the exact prose in the modal before Approve & Send. Reads the
    match_result's invoice (via LEFT JOIN) for amount/invoice_number/
    date, and any existing supplier_contact for a friendly ``name``.
    """
    from app.whatsapp.chase_template import (
        ChaseTemplateContext,
        render_chase_body,
    )

    row = session.execute(
        text(
            """
            SELECT
                mr.bucket::text AS bucket,
                COALESCE(i.counterparty_gstin, be.supplier_gstin) AS supplier_gstin,
                i.invoice_number,
                i.invoice_date,
                i.total_paise,
                cf.name AS firm_name,
                sc.name AS supplier_name
            FROM match_result mr
            LEFT JOIN invoice i ON i.id = mr.invoice_id
            LEFT JOIN b2b_entry be ON be.id = mr.b2b_entry_id
            LEFT JOIN ca_firm cf ON cf.id = mr.firm_id
            LEFT JOIN supplier_contact sc
                   ON sc.firm_id = mr.firm_id
                  AND sc.supplier_gstin = COALESCE(i.counterparty_gstin, be.supplier_gstin)
            WHERE mr.id = :id
            """
        ),
        {"id": str(match_result_id)},
    ).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="match_result_not_found")
    if row["bucket"] != "supplier_default":
        raise HTTPException(
            status_code=400,
            detail="chase preview only applies to supplier_default matches",
        )
    if not row["supplier_gstin"]:
        raise HTTPException(
            status_code=422, detail="match_result has no resolvable supplier_gstin"
        )

    ctx = ChaseTemplateContext(
        firm_name=row["firm_name"] or "your CA firm",
        supplier_name=row["supplier_name"] or "",
        supplier_gstin=row["supplier_gstin"],
        invoice_number=row["invoice_number"] or "",
        invoice_date_iso=(
            row["invoice_date"].isoformat()
            if row["invoice_date"] is not None
            else ""
        ),
        invoice_amount_paise=int(row["total_paise"] or 0),
    )
    body = render_chase_body(ctx, language=language)  # type: ignore[arg-type]
    return ChasePreviewResp(
        language=language,
        template_name=settings.whatsapp_template_chase_name,
        body=body,
        supplier_name=row["supplier_name"] or None,
        supplier_gstin=row["supplier_gstin"],
        firm_name=row["firm_name"] or "your CA firm",
    )


@router.get("/attempts", response_model=list[DeliveryAttemptRow])
def list_attempts(
    user: AppUser = Depends(get_current_user),
    session=Depends(get_firm_scoped_session),
    delivery_request_id: Optional[uuid.UUID] = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[DeliveryAttemptRow]:
    where = ["firm_id = :fid"]
    params: dict = {"fid": str(user.firm_id), "limit": limit}
    if delivery_request_id:
        where.append("delivery_request_id = :drid")
        params["drid"] = str(delivery_request_id)
    sql = (
        "SELECT id, delivery_request_id, provider, status, "
        "provider_message_id, error_kind, error_message, "
        "attempted_at, delivered_at, read_at, failed_at "
        "FROM delivery_attempt "
        f"WHERE {' AND '.join(where)} "
        "ORDER BY attempted_at DESC LIMIT :limit"
    )
    rows = session.execute(text(sql), params).mappings().all()
    return [DeliveryAttemptRow(**dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# Webhook — machine-authed via HMAC. Do NOT accept user JWTs here.
# Meta also does a GET verify handshake on webhook registration; we
# support both.
# ---------------------------------------------------------------------------


@router.get("/webhook")
def webhook_verify(
    hub_mode: Optional[str] = Query(default=None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(default=None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(default=None, alias="hub.challenge"),
) -> str:
    """Meta's one-time subscription verify. Return the challenge iff the
    verify_token matches what we configured out-of-band."""
    if hub_mode != "subscribe":
        raise HTTPException(status_code=400, detail="bad_mode")
    expected = settings.whatsapp_webhook_verify_token or ""
    if not expected:
        raise HTTPException(status_code=503, detail="webhook_unconfigured")
    import hmac

    if not hmac.compare_digest(expected, hub_verify_token or ""):
        raise HTTPException(status_code=403, detail="bad_verify_token")
    return hub_challenge or ""


@router.post("/webhook")
async def webhook_receive(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(default=None, alias="X-Hub-Signature-256"),
) -> dict:
    """Meta delivery status callbacks. HMAC-signed with the WABA app secret.

    We always return 200 to Meta (even on parse failure) so they do not
    aggressively retry — but only apply updates if the signature checks.
    A bad signature is loud in logs but returns 200 to avoid a signal
    that would let an attacker probe our secret.
    """
    body = await request.body()
    ok = webhook.verify_signature(
        body=body,
        header_value=x_hub_signature_256,
        app_secret=settings.whatsapp_app_secret,
    )
    if not ok:
        import logging

        logging.getLogger("niyam.whatsapp.webhook").warning(
            "whatsapp.webhook signature_invalid"
        )
        return {"status": "ignored"}
    import json as _json

    try:
        payload = _json.loads(body.decode("utf-8"))
    except Exception:
        return {"status": "ignored_bad_json"}
    events = webhook.parse_status_events(payload)
    updated = service.apply_webhook_events(events)
    return {"status": "ok", "updated": updated}
