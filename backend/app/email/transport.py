"""Transport protocol + in-repo implementations.

Real transports (SMTP, SES, Resend, Postmark) plug into ``EmailTransport``
so the invite / reset-password code paths stay identical regardless of
what actually delivers the bytes.
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage as _MIMEMessage
from email.utils import formataddr
from typing import Protocol


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    """One outbound email. Text-only for MVP."""

    to: str
    subject: str
    body_text: str
    from_addr: str
    from_name: str

    @property
    def from_header(self) -> str:
        # RFC 5322 display form. Kept trivial — production SMTP transports
        # will want proper MIME encoding of non-ASCII display names.
        return f"{self.from_name} <{self.from_addr}>" if self.from_name else self.from_addr


class EmailTransport(Protocol):
    def send(self, msg: EmailMessage) -> None:  # pragma: no cover - protocol
        ...


class ConsoleTransport:
    """Logs the message via observability. Never touches the network.

    Used as the ``email_enabled=True`` dev default so operators can eyeball
    the outbound payload in ``/livez``-adjacent structured logs before
    provisioning a real transport.
    """

    def send(self, msg: EmailMessage) -> None:
        logger.info(
            "email.dispatch",
            extra={
                "email_to": msg.to,
                "email_from": msg.from_header,
                "email_subject": msg.subject,
                "email_body_preview": msg.body_text[:200],
            },
        )


@dataclass
class MemoryTransport:
    """Test-only. Appends every send into ``sent`` for assertions."""

    sent: list[EmailMessage] = field(default_factory=list)

    def send(self, msg: EmailMessage) -> None:
        self.sent.append(msg)

    def clear(self) -> None:
        self.sent.clear()


class NoopTransport:
    """Silently drops every send. Used when ``email_enabled=False``.

    We do NOT raise here — the invite endpoint expects a call to
    ``get_transport().send(...)`` to be a safe no-op when the operator
    hasn't opted in to email yet. The UI copy-URL surface is the
    contract-guaranteed fallback in that mode.
    """

    def send(self, msg: EmailMessage) -> None:
        return None


@dataclass
class SMTPTransport:
    """Production SMTP transport. Supports three common TLS modes:

    * ``use_tls=True``        — SMTP_SSL on port 465 (implicit TLS).
    * ``use_starttls=True``   — plain SMTP + STARTTLS upgrade on port 587
                                (explicit TLS, most cloud relays).
    * neither                 — plain SMTP on port 25 (trusted internal relay).

    A new connection is opened per ``send()`` call — no persistent pool.
    This is intentional: transactional email volume is low (one per invite /
    reset) and a stale persistent connection would require reconnect logic.
    If volume ever warrants pooling, swap to an SMTP connection pool.

    Compatible with any SMTP relay: Mailgun, Postmark, SendGrid, AWS SES
    (via their SMTP interface), or a bare Postfix/Exim.
    """

    host: str
    port: int = 587
    username: str = ""
    password: str = ""
    use_tls: bool = False       # True for port 465 (SMTP_SSL / implicit TLS)
    use_starttls: bool = True   # True for port 587 (STARTTLS / explicit TLS)
    timeout: int = 30

    def send(self, msg: EmailMessage) -> None:
        mime = _MIMEMessage()
        mime["Subject"] = msg.subject
        mime["From"] = formataddr((msg.from_name, msg.from_addr))
        mime["To"] = msg.to
        mime.set_content(msg.body_text)

        if self.use_tls:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(self.host, self.port, context=ctx, timeout=self.timeout) as conn:
                if self.username:
                    conn.login(self.username, self.password)
                conn.send_message(mime)
        else:
            with smtplib.SMTP(self.host, self.port, timeout=self.timeout) as conn:
                if self.use_starttls:
                    conn.starttls(context=ssl.create_default_context())
                if self.username:
                    conn.login(self.username, self.password)
                conn.send_message(mime)
