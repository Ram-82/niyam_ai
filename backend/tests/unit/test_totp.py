"""Unit tests for TOTP wrapping around pyotp."""
from __future__ import annotations

import pyotp

from app.auth.totp import generate_secret, provisioning_uri, verify_totp


def test_generate_secret_is_base32_and_long_enough() -> None:
    secret = generate_secret()
    assert isinstance(secret, str)
    assert len(secret) >= 16  # pyotp default is 32 base32 chars
    # base32 alphabet
    assert set(secret) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567=")


def test_provisioning_uri_shape() -> None:
    secret = generate_secret()
    uri = provisioning_uri(secret, "user@example.com", issuer="Niyam AI")
    assert uri.startswith("otpauth://totp/")
    assert "issuer=Niyam%20AI" in uri
    assert secret in uri


def test_verify_accepts_current_code() -> None:
    secret = generate_secret()
    code = pyotp.TOTP(secret).now()
    assert verify_totp(secret, code)


def test_verify_rejects_wrong_code() -> None:
    secret = generate_secret()
    assert not verify_totp(secret, "000000")
    assert not verify_totp(secret, "abcdef")


def test_verify_rejects_empty_inputs() -> None:
    assert not verify_totp("", "123456")
    assert not verify_totp("ABCDEF234567ABCDEF234567", "")
