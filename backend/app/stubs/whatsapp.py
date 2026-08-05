"""WhatsApp delivery stub — shim to :mod:`app.whatsapp`.

The stub used to hard-raise so P1 send buttons could not silently
swallow a real send. The real implementation now lives in
``app/whatsapp/`` and this module is a compatibility shim:

* ``send_report`` + ``send_supplier_chase`` route through the new
  service, but the legacy positional signatures make the CA-approval
  gate awkward — so the shim raises :class:`WhatsAppUnavailable`
  UNLESS both a matching approved ``delivery_request`` exists AND
  the feature flag is on. That preserves the P1 posture (no silent
  send) while allowing new code paths that use the service directly
  to work uninterrupted.

Prefer importing from ``app.whatsapp.service`` in new code.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID


class WhatsAppUnavailable(RuntimeError):
    """Kept for import compatibility — the legacy positional API can no
    longer send safely because it lacks the delivery_request_id needed
    to enforce the CA-approval gate."""


def send_report(
    client_id: UUID,
    pdf_bytes: bytes,
    voice_note_bytes: Optional[bytes] = None,
) -> None:
    raise WhatsAppUnavailable(
        "The legacy send_report(client_id, pdf_bytes) API cannot enforce "
        "the CA-approval gate. Use app.whatsapp.service.send("
        "delivery_request_id=...) after the CA approves via "
        "POST /whatsapp/delivery-requests/{id}/approve."
    )


def send_supplier_chase(
    supplier_gstin: str,
    invoice_number: str,
    amount_paise: int,
    language: str,
) -> None:
    raise WhatsAppUnavailable(
        "The legacy send_supplier_chase API cannot enforce the "
        "NearMissReview gate. Use app.whatsapp.service.send("
        "delivery_request_id=...) with a delivery_request whose purpose="
        "'supplier_chase' points at a match_result carrying "
        "context.near_miss_reviewed_at."
    )
