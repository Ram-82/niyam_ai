"""Unit tests for the JWT encode/decode layer."""
from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from jose import jwt as jose_jwt

from app.auth.tokens import (
    ALGORITHM,
    TokenError,
    create_access_token,
    create_refresh_token,
    create_totp_setup_token,
    decode_token,
)
from app.config import settings


def _fake_user(role: str = "admin"):
    return SimpleNamespace(
        id=uuid.uuid4(),
        firm_id=uuid.uuid4(),
        role=role,
    )


def test_access_roundtrip() -> None:
    user = _fake_user()
    token, claims = create_access_token(user)
    decoded = decode_token(token)
    assert decoded.sub == str(user.id)
    assert decoded.firm_id == str(user.firm_id)
    assert decoded.typ == "access"
    assert decoded.jti == claims.jti


def test_refresh_roundtrip() -> None:
    user = _fake_user(role="staff")
    token, claims = create_refresh_token(user)
    decoded = decode_token(token)
    assert decoded.typ == "refresh"
    assert decoded.role == "staff"
    assert decoded.jti == claims.jti


def test_totp_setup_roundtrip() -> None:
    user = _fake_user()
    token, claims = create_totp_setup_token(user)
    decoded = decode_token(token)
    assert decoded.typ == "totp_setup"
    assert decoded.jti == claims.jti


def test_expired_token_rejected() -> None:
    user = _fake_user()
    payload = {
        "sub": str(user.id),
        "firm_id": str(user.firm_id),
        "role": "admin",
        "typ": "access",
        "jti": str(uuid.uuid4()),
        "iat": 1_700_000_000,
        "exp": 1_700_000_001,  # long past
    }
    tok = jose_jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)
    with pytest.raises(TokenError):
        decode_token(tok)


def test_wrong_secret_rejected() -> None:
    user = _fake_user()
    token, _ = create_access_token(user)
    # Re-sign a decoded payload with a different secret to prove it fails.
    bad = jose_jwt.encode(
        {"foo": "bar"}, "different-secret", algorithm=ALGORITHM
    )
    with pytest.raises(TokenError):
        decode_token(bad)


def test_each_token_has_unique_jti() -> None:
    user = _fake_user()
    seen = set()
    for _ in range(10):
        _, claims = create_access_token(user)
        assert claims.jti not in seen
        seen.add(claims.jti)
