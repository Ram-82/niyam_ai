"""WhatsApp Business API interface — P2.

**Intended contract.** In P2, ``send_report(client_id, pdf_bytes,
voice_note_bytes=None)`` uploads the CA-approved 2-pager (and optional
60-second voice-note MP3) to the WhatsApp Business Cloud API, addressed
to the phone number on ``client.metadata.whatsapp_number``. The message
must be templated (WhatsApp requires approved templates for
business-initiated conversations) and land as an INBOUND WHATSAPP
BUSINESS MESSAGE from the CA firm's registered WABA sender ID — i.e.
the client sees "Message from Ramesh & Co Chartered Accountants" (the
firm's white-labelled brand), not "Message from Niyam AI." This is a
positioning non-negotiable: the CA looks premium, which is why the CA
pays.

Return value is the WhatsApp message ID for audit-log tracking. The
outbound event writes to ``audit_log`` with ``action='report.sent'``
and links the message id to the source ``readiness_snapshot``.

**Why stubbed in P1.** WhatsApp Business API onboarding is a multi-
week bureaucratic pipeline (Facebook Business Manager, phone number
verification, template review). None of it is meaningful without a
signed pilot CA firm to onboard as the sender. P1's UI shows
``<StubBadge>WhatsApp report delivery</StubBadge>`` next to any
placeholder send buttons.

Also expected in the P2 implementation:

* ``send_supplier_chase(supplier_gstin, invoice_number, amount_paise,
  language)`` — the ``supplier_default`` chase flow. Must respect the
  ``NearMissReview`` gate on the CA side (see criterion #2 of step 9)
  — the API here just does delivery, never decides to chase.
* Delivery receipts + read-status webhooks that update
  ``readiness_snapshot.arithmetic`` follow-up state.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID


class WhatsAppUnavailable(RuntimeError):
    """Raised so P1 send buttons cannot silently swallow a real send."""


def send_report(
    client_id: UUID,
    pdf_bytes: bytes,
    voice_note_bytes: Optional[bytes] = None,
) -> None:
    raise WhatsAppUnavailable(
        "WhatsApp delivery is stubbed in P1. Vernacular 2-pager ships in P3, "
        "delivery in P4."
    )


def send_supplier_chase(
    supplier_gstin: str,
    invoice_number: str,
    amount_paise: int,
    language: str,
) -> None:
    raise WhatsAppUnavailable(
        "Supplier chase is stubbed in P1. Do not bypass the NearMissReview "
        "gate on supplier_default rows — verify the register entry first."
    )
