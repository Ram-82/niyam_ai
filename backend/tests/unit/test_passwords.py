"""Unit tests for the password hashing + policy layer."""
from __future__ import annotations

import pytest

from app.auth.passwords import (
    WeakPasswordError,
    assert_password_strength,
    hash_password,
    verify_password,
)


def test_hash_roundtrip_accepts_correct_password() -> None:
    pw = "Correct-Horse-Battery-Staple-42"
    h = hash_password(pw)
    assert h != pw
    assert verify_password(pw, h)
    assert not verify_password("wrong password", h)


def test_hash_verify_survives_malformed_hash() -> None:
    # Never raise on a bad hash — return False.
    assert verify_password("anything", "not-a-bcrypt-hash") is False


def test_strength_accepts_strong_password() -> None:
    # 32-char passphrase with mixed classes; zxcvbn scores this 4/4.
    assert_password_strength("Correct-Horse-Battery-Staple-42")


def test_strength_rejects_short() -> None:
    with pytest.raises(WeakPasswordError):
        assert_password_strength("aB3!xY9?")  # 8 chars


def test_strength_rejects_predictable_but_long() -> None:
    # 14 chars, meets length, but zxcvbn scores this 0.
    with pytest.raises(WeakPasswordError):
        assert_password_strength("password123456")
