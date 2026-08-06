"""Email dispatch — thin transport abstraction + high-level service.

Public surface:

* ``EmailTransport`` protocol       — send(msg) contract
* ``ConsoleTransport``              — dev / audit fallback (logs the message)
* ``MemoryTransport``               — tests only, records sends into a list
* ``NoopTransport``                 — used when email_enabled=False
* ``get_transport()``               — factory; returns the configured instance
* ``send_invite_email(...)``        — invite template + dispatch
* ``send_password_reset_email(...)``— reset template + dispatch (Tier-2 next)

All templates are plain text for MVP; HTML variants land when a real SMTP/
SES transport is wired up.
"""
from app.email.transport import (
    EmailMessage,
    EmailTransport,
    ConsoleTransport,
    MemoryTransport,
    NoopTransport,
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
    "get_transport",
    "reset_transport_for_tests",
    "send_due_date_reminder_email",
    "send_invite_email",
    "send_password_reset_email",
]
