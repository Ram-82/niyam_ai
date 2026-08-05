"""HMAC signature verification + payload → status-event parsing.

Meta signs webhook POSTs with ``X-Hub-Signature-256`` (``sha256=<hex>``)
computed as HMAC-SHA256 over the raw request body using the WABA app
secret. We verify constant-time and refuse any request that does not
match — an unsigned callback is a spoof and updating delivery_attempt
rows from a spoof would let an attacker mark a message as read/failed
without touching Meta.

The webhook payload shape is documented at:
https://developers.facebook.com/docs/whatsapp/cloud-api/webhooks/payload-examples

We normalise the "statuses" entries into :class:`WebhookStatusEvent`
records and hand them to the service in a straight list.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from app.whatsapp.types import WebhookStatusEvent


log = logging.getLogger("niyam.whatsapp.webhook")


def verify_signature(
    *,
    body: bytes,
    header_value: str | None,
    app_secret: str,
) -> bool:
    """Return True iff the signature is valid AND non-empty.

    Rejects any missing/malformed header immediately. Uses
    ``hmac.compare_digest`` so a partial-match timing side channel does
    not leak the correct prefix.
    """
    if not app_secret:
        # Reject rather than "no secret configured → accept everything".
        log.warning("whatsapp.webhook.signature_check app_secret_empty")
        return False
    if not header_value or not header_value.startswith("sha256="):
        return False
    expected = header_value.split("=", 1)[1].strip().lower()
    if not expected:
        return False
    digest = hmac.new(
        app_secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(digest, expected)


def parse_status_events(payload: dict[str, Any]) -> list[WebhookStatusEvent]:
    """Extract per-message status updates from a Meta webhook payload.

    Meta wraps updates in ``entry[].changes[].value.statuses[]``. Non-status
    events (message_template_status_update, inbound messages, etc.) are
    ignored — this function returns only the delivery-status events we
    act on.
    """
    out: list[WebhookStatusEvent] = []
    for entry in payload.get("entry", []) or []:
        for change in entry.get("changes", []) or []:
            value = change.get("value") or {}
            for st in value.get("statuses", []) or []:
                message_id = st.get("id")
                status = st.get("status")
                ts = st.get("timestamp")
                if not message_id or not status:
                    continue
                try:
                    at_epoch = int(ts) if ts is not None else 0
                except (TypeError, ValueError):
                    at_epoch = 0
                error_kind = None
                error_message = None
                errors = st.get("errors") or []
                if errors:
                    e0 = errors[0]
                    error_kind = str(e0.get("code")) if e0.get("code") is not None else None
                    error_message = e0.get("title") or e0.get("message")
                out.append(
                    WebhookStatusEvent(
                        provider_message_id=message_id,
                        status=status,
                        at_epoch=at_epoch,
                        error_kind=error_kind,
                        error_message=error_message,
                    )
                )
    return out
