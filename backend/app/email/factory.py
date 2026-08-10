"""Transport selection.

Reads ``settings.email_enabled`` + ``settings.email_mode`` at first call
and caches the transport for the process lifetime. Tests can flip modes
via ``reset_transport_for_tests()``.
"""
from __future__ import annotations

from typing import Optional

from app.config import settings
from app.email.transport import (
    ConsoleTransport,
    EmailTransport,
    MemoryTransport,
    NoopTransport,
    SMTPTransport,
)


_transport: Optional[EmailTransport] = None


def _build() -> EmailTransport:
    if not settings.email_enabled:
        return NoopTransport()
    mode = settings.email_mode.lower()
    if mode == "console":
        return ConsoleTransport()
    if mode == "memory":
        return MemoryTransport()
    if mode == "smtp":
        return SMTPTransport(
            host=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            use_starttls=settings.smtp_use_starttls,
        )
    # SES / Resend / Postmark land in follow-up slices; explicit error beats
    # silently no-oping and losing outbound mail.
    raise RuntimeError(
        f"email_mode={settings.email_mode!r} is not implemented yet. "
        "Supported modes: console, smtp. Set EMAIL_ENABLED=false to disable."
    )


def get_transport() -> EmailTransport:
    global _transport
    if _transport is None:
        _transport = _build()
    return _transport


def reset_transport_for_tests(transport: Optional[EmailTransport] = None) -> None:
    """Reset the cached transport. If ``transport`` is given, install it
    verbatim (bypasses settings). Otherwise the next ``get_transport()``
    call re-reads settings and rebuilds.
    """
    global _transport
    _transport = transport
