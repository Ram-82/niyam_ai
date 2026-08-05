"""Unit tests for the GSP application-layer AEAD."""
from __future__ import annotations

import base64
import os
import secrets

import pytest

from app.gsp import crypto


def test_encrypt_roundtrip_current_key() -> None:
    ct, kv = crypto.encrypt("sensitive-token-value")
    assert isinstance(ct, bytes)
    assert kv == crypto.current_key_version()
    assert crypto.decrypt(ct, kv) == "sensitive-token-value"


def test_ciphertext_is_never_equal_to_plaintext() -> None:
    ct, _ = crypto.encrypt("secret")
    assert b"secret" not in ct


def test_two_encryptions_of_same_input_produce_different_ciphertext() -> None:
    """Random 96-bit nonce guarantees non-determinism."""
    a, _ = crypto.encrypt("same-input")
    b, _ = crypto.encrypt("same-input")
    assert a != b


def test_tampered_ciphertext_fails_auth() -> None:
    ct, kv = crypto.encrypt("payload")
    # Flip one byte in the ciphertext tail (AEAD auth tag lives at the end).
    tampered = bytearray(ct)
    tampered[-1] ^= 0x01
    with pytest.raises(Exception):
        crypto.decrypt(bytes(tampered), kv)


def test_unknown_key_version_is_rejected() -> None:
    ct, _ = crypto.encrypt("payload")
    with pytest.raises(ValueError, match="unknown GSP key version"):
        crypto.decrypt(ct, key_version=999)


def test_reload_keys_supports_rotation(monkeypatch) -> None:
    """Simulate a rotation: add a new key at higher version, verify
    it becomes CURRENT while the old key still decrypts prior rows."""
    # Encrypt at v1 (dev default).
    ct_v1, kv_v1 = crypto.encrypt("prior-value")
    assert kv_v1 == 1

    new_key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")
    old_key_b64 = base64.urlsafe_b64encode(
        crypto._KEYS[1]  # type: ignore[attr-defined]
    ).decode("ascii")
    monkeypatch.setenv(
        "GSP_ENCRYPTION_KEYS", f"2:{new_key},1:{old_key_b64}"
    )
    try:
        crypto.reload_keys()
        assert crypto.current_key_version() == 2
        # New writes use v2:
        ct_v2, kv_v2 = crypto.encrypt("post-rotate")
        assert kv_v2 == 2
        # Prior v1 row still readable:
        assert crypto.decrypt(ct_v1, kv_v1) == "prior-value"
        # New row round-trips:
        assert crypto.decrypt(ct_v2, kv_v2) == "post-rotate"
    finally:
        monkeypatch.delenv("GSP_ENCRYPTION_KEYS", raising=False)
        crypto.reload_keys()


def test_empty_plaintext_rejected() -> None:
    with pytest.raises(ValueError):
        crypto.encrypt("")
