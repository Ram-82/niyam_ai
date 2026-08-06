"""Email transport + service — unit-level coverage.

Endpoint dispatch is covered by tests/integration/test_invite_email.py.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.email import (
    ConsoleTransport,
    EmailMessage,
    MemoryTransport,
    NoopTransport,
    factory,
    reset_transport_for_tests,
    send_invite_email,
    send_password_reset_email,
)


@pytest.fixture(autouse=True)
def _install_memory_transport():
    mem = MemoryTransport()
    reset_transport_for_tests(mem)
    yield mem
    reset_transport_for_tests(None)


def _sample_expiry() -> datetime:
    return datetime(2026, 8, 20, 15, 30, tzinfo=timezone.utc)


def test_invite_email_renders_url_subject_and_expiry(_install_memory_transport):
    mem = _install_memory_transport
    send_invite_email(
        to="new@example.com",
        invite_token="rawtoken123",
        inviter_email="admin@example.com",
        firm_name="Acme CA LLP",
        role="staff",
        expires_at=_sample_expiry(),
    )
    assert len(mem.sent) == 1
    msg = mem.sent[0]
    assert msg.to == "new@example.com"
    assert "Acme CA LLP" in msg.subject
    # The raw token MUST land in the body — that's how the recipient
    # actually accepts the invite.
    assert "rawtoken123" in msg.body_text
    assert "/register?token=rawtoken123" in msg.body_text
    # Absolute URL — we cannot ship relative links in an email.
    assert msg.body_text.count("http") >= 1
    # Expiry printed in ISO-like UTC form (locale-independent).
    assert "2026-08-20" in msg.body_text
    # Inviter identity shown for social proof.
    assert "admin@example.com" in msg.body_text


def test_password_reset_email_renders_url_and_expiry(_install_memory_transport):
    mem = _install_memory_transport
    send_password_reset_email(
        to="user@example.com",
        reset_token="resettok",
        expires_at=_sample_expiry(),
    )
    assert len(mem.sent) == 1
    msg = mem.sent[0]
    assert "/reset-password?token=resettok" in msg.body_text
    assert msg.subject.lower().startswith("reset")


def test_noop_transport_silently_drops():
    n = NoopTransport()
    # Must not raise regardless of message shape.
    n.send(EmailMessage(
        to="a@b.c", subject="s", body_text="b", from_addr="f@x.y", from_name="n",
    ))


def test_console_transport_does_not_raise(caplog):
    ConsoleTransport().send(EmailMessage(
        to="a@b.c",
        subject="hello",
        body_text="body preview here",
        from_addr="f@x.y",
        from_name="Niyam AI",
    ))
    # The observability layer swallows this in prod, but a smoke assertion
    # here catches accidental broken f-strings in the log call.


def test_from_header_formatting():
    msg = EmailMessage(
        to="t@e.co", subject="s", body_text="b",
        from_addr="from@ex.com", from_name="Display Name",
    )
    assert msg.from_header == "Display Name <from@ex.com>"


def test_factory_returns_noop_when_disabled(monkeypatch):
    reset_transport_for_tests(None)
    monkeypatch.setattr(factory.settings, "email_enabled", False)
    t = factory.get_transport()
    assert isinstance(t, NoopTransport)


def test_factory_console_when_enabled(monkeypatch):
    reset_transport_for_tests(None)
    monkeypatch.setattr(factory.settings, "email_enabled", True)
    monkeypatch.setattr(factory.settings, "email_mode", "console")
    t = factory.get_transport()
    assert isinstance(t, ConsoleTransport)


def test_factory_unknown_mode_raises(monkeypatch):
    reset_transport_for_tests(None)
    monkeypatch.setattr(factory.settings, "email_enabled", True)
    monkeypatch.setattr(factory.settings, "email_mode", "quantum")
    with pytest.raises(RuntimeError, match="not implemented"):
        factory.get_transport()
