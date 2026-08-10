"""Automated (fire-and-forget) WhatsApp notifications for internal events.

Unlike the delivery_request flow — which requires CA approval and logs
to delivery_attempt — these are system-to-CA notifications with no
approval gate. Best-effort: a transport error is logged as a warning and
never propagates to the caller.

Two event types shipped in P1:
  * ``recon_complete``     — after reconcile_period() succeeds
  * ``due_date_reminder``  — alongside the reminder sweep email

Both read ``ca_firm.admin_whatsapp_number`` (nullable). A NULL number
means the firm has not opted in; the function returns silently.

Template names must match pre-registered Meta WABA templates. In mock
mode the transport records the call without making any real API call.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from sqlalchemy import text

from app.db import owner_engine

log = logging.getLogger("niyam.whatsapp.notify")


def _firm_admin_whatsapp(firm_id: str) -> Optional[str]:
    with owner_engine.begin() as conn:
        row = conn.execute(
            text("SELECT admin_whatsapp_number FROM ca_firm WHERE id = :id"),
            {"id": firm_id},
        ).first()
    return row[0] if row else None


def _do_send(
    to_e164: str,
    template_name: str,
    template_lang: str,
    body_params: list[str],
) -> None:
    from app.whatsapp.service import get_transport
    from app.whatsapp.types import WhatsAppDisabled, WhatsAppError

    try:
        transport = get_transport()
    except WhatsAppDisabled:
        return
    except Exception:
        log.warning("notify._do_send.transport_error", exc_info=True)
        return

    try:
        transport.send_template(
            to_e164=to_e164,
            template_name=template_name,
            template_lang=template_lang,
            components=[
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": p} for p in body_params
                    ],
                }
            ],
        )
    except WhatsAppError:
        log.warning("notify._do_send.send_failed", exc_info=True)


def recon_complete(
    *,
    firm_id: str,
    gstin: str,
    period: str,
    run_id: str,
    matched: int,
    probable: int,
    supplier_default: int,
    missing: int,
) -> None:
    """Notify the firm admin that a reconciliation run has completed.

    Template ``niyam_recon_complete`` parameters (in order):
      {{1}} GSTIN
      {{2}} Period  (e.g. "2026-07")
      {{3}} Matched count
      {{4}} Probable count
      {{5}} Unmatched (supplier_default) count
      {{6}} Missing count
    """
    number = _firm_admin_whatsapp(firm_id)
    if not number:
        return
    period_display = f"{period[:4]}-{period[4:]}"
    _do_send(
        to_e164=number,
        template_name="niyam_recon_complete",
        template_lang="en_US",
        body_params=[
            gstin,
            period_display,
            str(matched),
            str(probable),
            str(supplier_default),
            str(missing),
        ],
    )
    log.info(
        "notify.recon_complete.sent",
        extra={"firm_id": firm_id, "run_id": run_id, "gstin": gstin},
    )


def due_date_reminder(
    *,
    firm_id: str,
    gstin: str,
    client_trade_name: str,
    return_type: str,
    period: str,
    days_before_due: int,
    due_date: date,
) -> None:
    """Notify the firm admin about an upcoming GST due date via WhatsApp.

    Template ``niyam_due_date_reminder`` parameters (in order):
      {{1}} Client trade name
      {{2}} GSTIN
      {{3}} Return type  (GSTR1 / GSTR3B)
      {{4}} Period display  (e.g. "2026-07")
      {{5}} Due date  (e.g. "11 Aug 2026")
      {{6}} Days remaining  ("today" when 0)
    """
    number = _firm_admin_whatsapp(firm_id)
    if not number:
        return
    period_display = f"{period[:4]}-{period[4:]}"
    days_str = "today" if days_before_due == 0 else str(days_before_due)
    _do_send(
        to_e164=number,
        template_name="niyam_due_date_reminder",
        template_lang="en_US",
        body_params=[
            client_trade_name,
            gstin,
            return_type,
            period_display,
            due_date.strftime("%d %b %Y"),
            days_str,
        ],
    )
    log.info(
        "notify.due_date_reminder.sent",
        extra={
            "firm_id": firm_id,
            "gstin": gstin,
            "return_type": return_type,
            "period": period,
            "days_before_due": days_before_due,
        },
    )
