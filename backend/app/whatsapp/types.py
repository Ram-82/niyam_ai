"""Data contracts + Protocol + exception taxonomy for WhatsApp delivery.

Mirrors the shape of :mod:`app.gsp.client` — a fixed error taxonomy the
service layer maps to typed exceptions, and a Transport Protocol both
adapters (mock + Meta Cloud API) implement.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional, Protocol


# Meta's language tags per their template convention.
TemplateLanguage = str  # 'en_US' | 'hi_IN' | 'kn_IN' | 'mr_IN'
LANGUAGE_TO_TEMPLATE_LANG: dict[str, str] = {
    "en": "en_US",
    "hi": "hi_IN",
    "kn": "kn_IN",
    "mr": "mr_IN",
}


# E.164 loose match — leading '+', 8-15 digits. Meta requires E.164 and
# will reject anything else with a 400.
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def is_valid_e164(number: str) -> bool:
    return bool(_E164_RE.match(number))


class WhatsAppErrorKind(str, Enum):
    TEMPLATE_NOT_APPROVED = "template_not_approved"
    INVALID_NUMBER = "invalid_number"
    RATE_LIMITED = "rate_limited"
    META_5XX = "meta_5xx"
    OTHER = "other"


class WhatsAppError(RuntimeError):
    """Base class for adapter-surfaced failures."""

    kind: WhatsAppErrorKind = WhatsAppErrorKind.OTHER
    http_status: Optional[int] = None
    retry_after_seconds: Optional[int] = None

    def __init__(
        self,
        message: str,
        *,
        http_status: Optional[int] = None,
        retry_after_seconds: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds


class TemplateNotApproved(WhatsAppError):
    kind = WhatsAppErrorKind.TEMPLATE_NOT_APPROVED


class InvalidNumber(WhatsAppError):
    kind = WhatsAppErrorKind.INVALID_NUMBER


class RateLimited(WhatsAppError):
    kind = WhatsAppErrorKind.RATE_LIMITED


class MetaServerError(WhatsAppError):
    kind = WhatsAppErrorKind.META_5XX


# ---------------------------------------------------------------------------
# Gate-side exceptions — raised by ``app.whatsapp.gate`` before any
# transport call. The API layer maps these to 4xx responses.
# ---------------------------------------------------------------------------


class ApprovalMissing(RuntimeError):
    """delivery_request has no ``approved_at``. CA must approve first."""


class NearMissReviewMissing(RuntimeError):
    """supplier_chase requested but the referenced match_result has no
    ``context.near_miss_reviewed_at`` — step-9 gate."""


class WhatsAppDisabled(RuntimeError):
    """Feature flag off. Endpoint returns 503."""


class DeliveryRequestUnknown(RuntimeError):
    """delivery_request_id does not resolve within the caller's firm."""


class DeliveryRequestLocked(RuntimeError):
    """delivery_request already has ``locked_at`` set. A new request is
    required to send again (audit)."""


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SendResult:
    provider: str
    provider_message_id: str
    status: str  # 'sent' initially — webhook events promote to delivered/read/failed


class Transport(Protocol):
    """Adapter interface. See ``transport_mock`` and ``transport_meta``.

    Both operations must be idempotent-safe from the service's POV — the
    service opens a delivery_attempt row BEFORE calling send_template so
    a duplicate send never happens without a durable record.
    """

    provider: str

    def send_template(
        self,
        *,
        to_e164: str,
        template_name: str,
        template_lang: TemplateLanguage,
        media_bytes: Optional[bytes] = None,
        media_mime: Optional[str] = None,
        components: Optional[list[dict[str, Any]]] = None,
    ) -> SendResult:  # pragma: no cover
        ...


# ---------------------------------------------------------------------------
# Webhook payload shape (subset of Meta's schema we actually read).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WebhookStatusEvent:
    """A single delivery status update parsed from a Meta webhook.

    Meta sends batched events; we normalise to one of these per status
    per message id so ``service.apply_webhook_status`` can process them
    in a straight loop.
    """

    provider_message_id: str
    status: str  # 'sent' | 'delivered' | 'read' | 'failed'
    at_epoch: int
    error_kind: Optional[str] = None
    error_message: Optional[str] = None
