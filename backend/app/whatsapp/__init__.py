"""WhatsApp Business Cloud API delivery + CA-approval gate.

Ships two send flows behind a hard approval gate:

* ``send_report(delivery_request_id, media_bytes)`` — the CA-approved
  2-pager. Precondition: a ``delivery_request`` row with
  ``purpose='report_send'``, ``approved_at IS NOT NULL``, referencing a
  ``narration_run``.
* ``send_supplier_chase(delivery_request_id)`` — the supplier_default
  outreach. Precondition: a ``delivery_request`` row with
  ``purpose='supplier_chase'``, ``approved_at IS NOT NULL``, referencing
  a ``match_result``, AND the match_result must carry
  ``context.near_miss_reviewed_at`` (step-9 acceptance criterion #2:
  never chase a supplier before reviewing the near-miss list).

Adapter contract: :mod:`.transport_mock` and :mod:`.transport_meta` both
implement the same Protocol so a dev deployment never depends on the
real Meta Cloud API being reachable.

The API surface lives in ``app/api/whatsapp.py``; delivery-side events
land on ``/whatsapp/webhook`` (HMAC-verified) and update
``delivery_attempt.status`` in place.
"""
