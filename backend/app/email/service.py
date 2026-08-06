"""High-level email dispatchers.

Each function renders a text template and hands the resulting
``EmailMessage`` to whatever transport ``get_transport()`` returns. Callers
never touch the transport directly.
"""
from __future__ import annotations

from datetime import datetime

from app.config import settings
from app.email.factory import get_transport
from app.email.transport import EmailMessage


def _fmt_expires(expires_at: datetime) -> str:
    # Render as YYYY-MM-DD HH:MM UTC — locale-independent, no ambiguity
    # for a CA reading the email in India while the server writes UTC.
    return expires_at.strftime("%Y-%m-%d %H:%M UTC")


def _build_url(path: str) -> str:
    base = settings.email_app_base_url.rstrip("/")
    if not path.startswith("/"):
        path = "/" + path
    return f"{base}{path}"


def send_invite_email(
    *,
    to: str,
    invite_token: str,
    inviter_email: str,
    firm_name: str,
    role: str,
    expires_at: datetime,
) -> EmailMessage:
    url = _build_url(f"/register?token={invite_token}")
    subject = f"You're invited to {firm_name} on Niyam AI"
    body = (
        f"{inviter_email} has invited you to join {firm_name} on Niyam AI\n"
        f"as a {role}.\n"
        f"\n"
        f"Accept the invite here (valid until {_fmt_expires(expires_at)}):\n"
        f"\n"
        f"  {url}\n"
        f"\n"
        f"If you weren't expecting this, ignore this email — the link\n"
        f"expires on its own.\n"
    )
    msg = EmailMessage(
        to=to,
        subject=subject,
        body_text=body,
        from_addr=settings.email_from,
        from_name=settings.email_from_name,
    )
    get_transport().send(msg)
    return msg


def send_password_reset_email(
    *,
    to: str,
    reset_token: str,
    expires_at: datetime,
) -> EmailMessage:
    url = _build_url(f"/reset-password?token={reset_token}")
    subject = "Reset your Niyam AI password"
    body = (
        f"A password reset was requested for this email.\n"
        f"\n"
        f"Set a new password here (valid until {_fmt_expires(expires_at)}):\n"
        f"\n"
        f"  {url}\n"
        f"\n"
        f"If you didn't request this, ignore the email — nothing changes\n"
        f"until the link is used, and it expires on its own.\n"
    )
    msg = EmailMessage(
        to=to,
        subject=subject,
        body_text=body,
        from_addr=settings.email_from,
        from_name=settings.email_from_name,
    )
    get_transport().send(msg)
    return msg
