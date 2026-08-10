"""Email dispatch — thin transport abstraction + high-level service.

Public surface:

* ``EmailTransport`` protocol       — send(msg) contract
* ``ConsoleTransport``              — dev / audit fallback (logs the message)
* ``MemoryTransport``               — tests only, records sends into a list
* ``NoopTransport``                 — used when email_enabled=False
* ``SMTPTransport``                 — production SMTP relay (Mailgun, SendGrid, SES, etc.)
* ``get_transport()``               — factory; returns the configured instance
* ``send_invite_email(...)``        — invite template + dispatch
* ``send_password_reset_email(...)``— reset template + dispatch

All templates are plain text; HTML variants are a follow-up.
"""
from app.email.transport import (
    EmailMessage,
    EmailTransport,
    ConsoleTransport,
    MemoryTransport,
    NoopTransport,
    SMTPTransport,
)
from app.email.factory import get_transport, reset_transport_for_tests
from app.email.service import (
    send_due_date_reminder_email,
    send_invite_email,
    send_password_reset_email,
)

__all__ = [
    "EmailMessage",
    "EmailTransport",
    "ConsoleTransport",
    "MemoryTransport",
    "NoopTransport",
    "SMTPTransport",
    "get_transport",
    "reset_transport_for_tests",
    "send_due_date_reminder_email",
    "send_invite_email",
    "send_password_reset_email",
]
