"""Application-layer AEAD for GSP session tokens.

The GSP session token is a bearer credential — anyone who reads
``gsp_session.token_ciphertext`` in the DB has nothing usable without
this module's key. That is the entire point: a leaked pg_dump or a
compromised read-only DB user cannot impersonate the taxpayer against
the GSP.

Design:

* AES-256-GCM via ``cryptography`` (AEAD; auth tag catches tamper).
* Random 96-bit nonce per encryption. Nonce is prepended to the
  ciphertext blob written to ``gsp_session.token_ciphertext`` so
  decryption needs only the key + the blob.
* Per-key version integer stored on the row (``key_version``). Rotation
  reads with the old key, re-encrypts with the new, bumps the int.

Key material:

* ``GSP_ENCRYPTION_KEYS`` env var — comma-separated list of
  ``<version>:<base64url_32_bytes>`` entries. The highest version is
  the CURRENT key (used for new writes). All versions are usable for
  reads until a rotation drops them.
* Falls back to a fixed dev-only key when the env var is unset AND
  ``GSP_MODE=mock`` — so `docker compose up` "just works". In any
  non-mock mode, an unset key is a hard startup error.

Rotation seam (documented in README):

    1. Generate new 32-byte key:
       ``python -c 'import secrets,base64;
                    print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())'``
    2. Prepend to ``GSP_ENCRYPTION_KEYS`` as ``<new_version>:<key>,<old>``.
    3. Roll the API + worker with the new env.
    4. Run ``python -m scripts.rotate_gsp_keys`` (Stage 4 ships it) —
       reads every ``gsp_session`` with ``key_version < current``,
       decrypts, re-encrypts, updates.
    5. Once no rows reference the old version, drop it from the env.
"""
from __future__ import annotations

import base64
import os
import secrets
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


NONCE_BYTES = 12  # AES-GCM standard 96-bit nonce
KEY_BYTES = 32    # AES-256


# Fixed dev-only key. Reused across `docker compose up` restarts so a
# session written before a restart can still be decrypted after. Any
# non-mock deployment MUST override via ``GSP_ENCRYPTION_KEYS``.
_DEV_KEY_B64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


class GspKeyMissing(RuntimeError):
    """Startup guard — GSP_ENCRYPTION_KEYS is required in non-mock mode."""


def _parse_keys(raw: str) -> dict[int, bytes]:
    keys: dict[int, bytes] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        version_s, _, key_s = entry.partition(":")
        if not version_s or not key_s:
            raise ValueError(f"bad GSP_ENCRYPTION_KEYS entry: {entry!r}")
        version = int(version_s)
        key = base64.urlsafe_b64decode(key_s.encode("ascii"))
        if len(key) != KEY_BYTES:
            raise ValueError(
                f"GSP key v{version} must be {KEY_BYTES} bytes, got {len(key)}"
            )
        keys[version] = key
    if not keys:
        raise ValueError("GSP_ENCRYPTION_KEYS parsed to no entries")
    return keys


def _load_keys() -> tuple[dict[int, bytes], int]:
    raw = os.getenv("GSP_ENCRYPTION_KEYS", "").strip()
    if raw:
        keys = _parse_keys(raw)
    else:
        if settings.gsp_mode != "mock":
            raise GspKeyMissing(
                "GSP_ENCRYPTION_KEYS must be set when GSP_MODE != 'mock'"
            )
        keys = {1: base64.urlsafe_b64decode(_DEV_KEY_B64.encode("ascii"))}
    current_version = max(keys.keys())
    return keys, current_version


# Loaded once at import time so a missing key crashes on startup, not
# per-request. Tests may monkey-patch _KEYS via ``reload_keys``.
_KEYS: dict[int, bytes]
_CURRENT_VERSION: int
_KEYS, _CURRENT_VERSION = _load_keys()


def reload_keys() -> None:
    """Re-read the env. Used by tests that install a rotation."""
    global _KEYS, _CURRENT_VERSION
    _KEYS, _CURRENT_VERSION = _load_keys()


def current_key_version() -> int:
    return _CURRENT_VERSION


def encrypt(plaintext: str) -> tuple[bytes, int]:
    """Encrypt ``plaintext`` under the current key. Returns (ciphertext_blob, key_version).

    Blob layout: ``nonce (12 bytes) || ciphertext_and_tag``. Store as-is
    in ``gsp_session.token_ciphertext``.
    """
    if not isinstance(plaintext, str) or not plaintext:
        raise ValueError("plaintext must be a non-empty string")
    key = _KEYS[_CURRENT_VERSION]
    nonce = secrets.token_bytes(NONCE_BYTES)
    ct = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return nonce + ct, _CURRENT_VERSION


def decrypt(blob: bytes, key_version: int) -> str:
    """Decrypt ``blob`` with the key at ``key_version``. Raise if unknown."""
    if len(blob) < NONCE_BYTES + 16:  # nonce + at least the 16-byte tag
        raise ValueError("ciphertext blob too short")
    key = _KEYS.get(key_version)
    if key is None:
        raise ValueError(
            f"unknown GSP key version {key_version} — has it been dropped from env?"
        )
    nonce, ct = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    plaintext = AESGCM(key).decrypt(nonce, ct, associated_data=None)
    return plaintext.decode("utf-8")
