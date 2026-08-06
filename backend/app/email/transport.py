"""Transport protocol + in-repo implementations.

Real transports (SMTP, SES, Resend, Postmark) plug into ``EmailTransport``
so the invite / reset-password code paths stay identical regardless of
what actually delivers the bytes.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
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
