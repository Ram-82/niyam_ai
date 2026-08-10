"""Unit tests for SMTPTransport and the factory's SMTP wiring.

smtplib is mocked so no network connection is required. The tests
verify the correct SMTP class is used, TLS is negotiated correctly,
authentication is passed when credentials are present, and the
message fields land in the outbound MIME envelope.
"""
from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from app.email import (
    EmailMessage,
    SMTPTransport,
    factory,
    reset_transport_for_tests,
)
from app.config import settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _msg(**kwargs) -> EmailMessage:
    defaults = {
        "to": "recipient@example.com",
        "subject": "Test subject",
        "body_text": "Hello from Niyam AI.",
        "from_addr": "no-reply@niyam.ai",
        "from_name": "Niyam AI",
    }
    defaults.update(kwargs)
    return EmailMessage(**defaults)


# ---------------------------------------------------------------------------
# STARTTLS path (port 587, default)
# ---------------------------------------------------------------------------


def test_starttls_opens_smtp_and_calls_starttls():
    transport = SMTPTransport(
        host="smtp.example.com",
        port=587,
        username="user",
        password="pass",
        use_tls=False,
        use_starttls=True,
    )
    mock_conn = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.return_value.__enter__ = lambda s: mock_conn
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
        transport.send(_msg())

    mock_smtp_cls.assert_called_once_with("smtp.example.com", 587, timeout=30)
    mock_conn.starttls.assert_called_once()
    mock_conn.login.assert_called_once_with("user", "pass")
    mock_conn.send_message.assert_called_once()


def test_starttls_skips_login_when_no_credentials():
    transport = SMTPTransport(
        host="relay.internal",
        port=587,
        username="",
        password="",
        use_tls=False,
        use_starttls=True,
    )
    mock_conn = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.return_value.__enter__ = lambda s: mock_conn
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
        transport.send(_msg())

    mock_conn.starttls.assert_called_once()
    mock_conn.login.assert_not_called()
    mock_conn.send_message.assert_called_once()


# ---------------------------------------------------------------------------
# Implicit TLS path (port 465, SMTP_SSL)
# ---------------------------------------------------------------------------


def test_smtp_ssl_uses_smtp_ssl_class():
    transport = SMTPTransport(
        host="smtp.example.com",
        port=465,
        username="user",
        password="secret",
        use_tls=True,
        use_starttls=False,
    )
    mock_conn = MagicMock()
    with patch("smtplib.SMTP_SSL") as mock_ssl_cls:
        mock_ssl_cls.return_value.__enter__ = lambda s: mock_conn
        mock_ssl_cls.return_value.__exit__ = MagicMock(return_value=False)
        transport.send(_msg())

    mock_ssl_cls.assert_called_once()
    args, kwargs = mock_ssl_cls.call_args
    assert args[0] == "smtp.example.com"
    assert args[1] == 465
    mock_conn.login.assert_called_once_with("user", "secret")
    mock_conn.send_message.assert_called_once()
    # Must NOT call starttls on an already-TLS connection.
    mock_conn.starttls.assert_not_called()


def test_smtp_ssl_skips_login_when_no_credentials():
    transport = SMTPTransport(
        host="smtp.example.com",
        port=465,
        username="",
        password="",
        use_tls=True,
        use_starttls=False,
    )
    mock_conn = MagicMock()
    with patch("smtplib.SMTP_SSL") as mock_ssl_cls:
        mock_ssl_cls.return_value.__enter__ = lambda s: mock_conn
        mock_ssl_cls.return_value.__exit__ = MagicMock(return_value=False)
        transport.send(_msg())

    mock_conn.login.assert_not_called()
    mock_conn.send_message.assert_called_once()


# ---------------------------------------------------------------------------
# Plain SMTP (trusted relay, no TLS)
# ---------------------------------------------------------------------------


def test_plain_smtp_skips_tls_and_starttls():
    transport = SMTPTransport(
        host="relay.internal",
        port=25,
        username="",
        password="",
        use_tls=False,
        use_starttls=False,
    )
    mock_conn = MagicMock()
    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.return_value.__enter__ = lambda s: mock_conn
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
        transport.send(_msg())

    mock_conn.starttls.assert_not_called()
    mock_conn.login.assert_not_called()
    mock_conn.send_message.assert_called_once()


# ---------------------------------------------------------------------------
# MIME envelope checks
# ---------------------------------------------------------------------------


def test_mime_fields_are_set_correctly():
    transport = SMTPTransport(
        host="smtp.example.com", port=587, username="", password="",
        use_tls=False, use_starttls=False,
    )
    mock_conn = MagicMock()
    captured = {}

    def capture_send_message(mime_msg):
        captured["msg"] = mime_msg

    mock_conn.send_message.side_effect = capture_send_message

    with patch("smtplib.SMTP") as mock_smtp_cls:
        mock_smtp_cls.return_value.__enter__ = lambda s: mock_conn
        mock_smtp_cls.return_value.__exit__ = MagicMock(return_value=False)
        transport.send(_msg(
            to="bob@example.com",
            subject="Your invite",
            body_text="Join us!",
            from_addr="no-reply@niyam.ai",
            from_name="Niyam AI",
        ))

    mime = captured["msg"]
    assert mime["To"] == "bob@example.com"
    assert mime["Subject"] == "Your invite"
    assert "niyam.ai" in mime["From"]
    assert mime.get_body().get_content().strip() == "Join us!"


# ---------------------------------------------------------------------------
# Factory wiring
# ---------------------------------------------------------------------------


def test_factory_returns_smtp_transport_when_mode_smtp(monkeypatch):
    reset_transport_for_tests(None)
    monkeypatch.setattr(factory.settings, "email_enabled", True)
    monkeypatch.setattr(factory.settings, "email_mode", "smtp")
    monkeypatch.setattr(factory.settings, "smtp_host", "smtp.mailgun.org")
    monkeypatch.setattr(factory.settings, "smtp_port", 587)
    monkeypatch.setattr(factory.settings, "smtp_username", "postmaster@mg.example.com")
    monkeypatch.setattr(factory.settings, "smtp_password", "secret")
    monkeypatch.setattr(factory.settings, "smtp_use_tls", False)
    monkeypatch.setattr(factory.settings, "smtp_use_starttls", True)

    t = factory.get_transport()
    assert isinstance(t, SMTPTransport)
    assert t.host == "smtp.mailgun.org"
    assert t.use_starttls is True
    reset_transport_for_tests(None)


# ---------------------------------------------------------------------------
# Startup validator
# ---------------------------------------------------------------------------


def test_config_raises_when_smtp_mode_missing_host(monkeypatch):
    from pydantic import ValidationError
    from app.config import Settings

    with pytest.raises((ValueError, ValidationError)):
        Settings(
            database_url="postgresql+psycopg://u:p@h/db",
            app_database_url="postgresql+psycopg://u:p@h/db",
            jwt_secret="x" * 32,
            email_enabled=True,
            email_mode="smtp",
            smtp_host="",   # missing — must raise
        )
