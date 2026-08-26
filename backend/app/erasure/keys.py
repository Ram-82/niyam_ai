"""Per-subject symmetric key management: allocate, wrap, unwrap, destroy.

Same envelope pattern as ``app.gsp.crypto`` (AES-256-GCM, versioned KEK
via env). This module wraps *subject keys*; the subject key itself
would later encrypt actual personal-data columns. That column-migration
work is out of scope for this pass — the mechanism ships now so the API
surface exists before the policy questions land.

Environment:
  ERASURE_KEK_KEYS — comma-separated ``<version>:<base64url_32_bytes>``.
                     Highest version is the CURRENT KEK.

  In mock mode (``GSP_MODE=mock``, checked via settings), falls back to
  a fixed dev-only key so ``docker compose up`` + tests just work.
  Anywhere else, missing env is a hard startup error via ``current_kek()``.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
import uuid
from dataclasses import dataclass
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings


NONCE_BYTES = 12
KEY_BYTES = 32


class ErasureKekMissing(RuntimeError):
    """Startup guard — ERASURE_KEK_KEYS is required outside mock mode."""


_DEV_KEK_B64 = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="


def _kek_checksum(kek: bytes) -> str:
    """First 16 hex chars of SHA-256(kek). Short enough to index cheaply,
    long enough (64 bits) that accidental collision between real KEKs is
    astronomically unlikely."""
    return hashlib.sha256(kek).hexdigest()[:16]


# Precomputed constant so callers can query for dev-KEK contamination
# without having to load the dev key first.
DEV_KEK_CHECKSUM: str = _kek_checksum(base64.b64decode(_DEV_KEK_B64))


def _parse_kek_env(raw: str) -> dict[int, bytes]:
    keys: dict[int, bytes] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        v_s, _, k_s = entry.partition(":")
        if not v_s or not k_s:
            raise ValueError(f"bad ERASURE_KEK_KEYS entry: {entry!r}")
        v = int(v_s)
        k = base64.urlsafe_b64decode(k_s.encode("ascii"))
        if len(k) != KEY_BYTES:
            raise ValueError(
                f"ERASURE KEK v{v} must be {KEY_BYTES} bytes, got {len(k)}"
            )
        keys[v] = k
    return keys


def _load_keks() -> dict[int, bytes]:
    raw = os.environ.get("ERASURE_KEK_KEYS", "").strip()
    if raw:
        return _parse_kek_env(raw)
    # Dev-only fallback in mock/test contexts. Any other mode = hard error.
    if getattr(settings, "gsp_mode", "mock") == "mock":
        return {1: base64.b64decode(_DEV_KEK_B64)}
    raise ErasureKekMissing(
        "ERASURE_KEK_KEYS env var is required outside mock mode"
    )


def assert_kek_available() -> None:
    """Startup guard. Fails fast if the environment is not mock and the KEK
    env is missing/malformed. Called from ``app.main._lifespan`` so the
    service refuses to boot rather than fail lazily at first key allocation."""
    _load_keks()


def current_kek() -> tuple[int, bytes]:
    keks = _load_keks()
    v = max(keks)
    return v, keks[v]


def _kek_for_version(version: int) -> bytes:
    keks = _load_keks()
    if version not in keks:
        raise KeyError(f"ERASURE KEK v{version} not present in env")
    return keks[version]


def _wrap(subject_key: bytes, kek: bytes) -> bytes:
    """Return nonce||ciphertext||tag using AES-GCM."""
    aead = AESGCM(kek)
    nonce = secrets.token_bytes(NONCE_BYTES)
    ct = aead.encrypt(nonce, subject_key, associated_data=None)
    return nonce + ct


def _unwrap(blob: bytes, kek: bytes) -> bytes:
    aead = AESGCM(kek)
    nonce, ct = blob[:NONCE_BYTES], blob[NONCE_BYTES:]
    return aead.decrypt(nonce, ct, associated_data=None)


@dataclass(frozen=True)
class SubjectKeyRow:
    id: uuid.UUID
    firm_id: uuid.UUID
    subject_kind: str
    subject_ref: str
    kek_version: int
    destroyed: bool


def allocate(
    session: Session,
    firm_id: uuid.UUID | str,
    subject_kind: str,
    subject_ref: str,
) -> SubjectKeyRow:
    """Create a new subject key or return the existing (non-destroyed) one.

    Idempotent per (firm_id, subject_kind, subject_ref) — the unique
    index enforces that. Re-allocating for a destroyed subject is
    NOT permitted here: destruction is meant to be irreversible.
    """
    existing = session.execute(
        text(
            """
            SELECT id, firm_id, subject_kind, subject_ref,
                   kek_version, destroyed_at
            FROM subject_key
            WHERE firm_id = CAST(:fid AS UUID)
              AND subject_kind = :kind
              AND subject_ref = :ref
            LIMIT 1
            """
        ),
        {"fid": str(firm_id), "kind": subject_kind, "ref": subject_ref},
    ).mappings().first()
    if existing is not None:
        if existing["destroyed_at"] is not None:
            raise ValueError(
                "subject key already destroyed — re-allocation is not permitted"
            )
        return SubjectKeyRow(
            id=existing["id"],
            firm_id=existing["firm_id"],
            subject_kind=existing["subject_kind"],
            subject_ref=existing["subject_ref"],
            kek_version=existing["kek_version"],
            destroyed=False,
        )

    subject_key = secrets.token_bytes(KEY_BYTES)
    version, kek = current_kek()
    wrapped = _wrap(subject_key, kek)
    checksum = _kek_checksum(kek)
    new_id = uuid.uuid4()
    session.execute(
        text(
            """
            INSERT INTO subject_key (
                id, firm_id, subject_kind, subject_ref,
                key_material, kek_version, kek_checksum
            ) VALUES (
                CAST(:id AS UUID), CAST(:fid AS UUID), :kind, :ref,
                :km, :kv, :kc
            )
            """
        ),
        {
            "id": str(new_id),
            "fid": str(firm_id),
            "kind": subject_kind,
            "ref": subject_ref,
            "km": wrapped,
            "kv": version,
            "kc": checksum,
        },
    )
    return SubjectKeyRow(
        id=new_id,
        firm_id=firm_id if isinstance(firm_id, uuid.UUID) else uuid.UUID(str(firm_id)),
        subject_kind=subject_kind,
        subject_ref=subject_ref,
        kek_version=version,
        destroyed=False,
    )


def unwrap(session: Session, subject_key_id: uuid.UUID | str) -> bytes:
    """Return the 32-byte subject key. Raises if destroyed or missing."""
    row = session.execute(
        text(
            """
            SELECT key_material, kek_version, destroyed_at
            FROM subject_key WHERE id = CAST(:id AS UUID)
            """
        ),
        {"id": str(subject_key_id)},
    ).mappings().first()
    if row is None:
        raise KeyError(subject_key_id)
    if row["destroyed_at"] is not None:
        raise ValueError("subject key destroyed")
    kek = _kek_for_version(row["kek_version"])
    return _unwrap(bytes(row["key_material"]), kek)


def destroy(session: Session, subject_key_id: uuid.UUID | str) -> None:
    """Zero the wrapped key_material and set destroyed_at.

    Once this returns the subject key is unrecoverable — any ciphertext
    that was written under it is now dead bytes.
    """
    result = session.execute(
        text(
            """
            UPDATE subject_key
            SET key_material = decode('00', 'hex'),
                destroyed_at = COALESCE(destroyed_at, now())
            WHERE id = CAST(:id AS UUID)
              AND destroyed_at IS NULL
            """
        ),
        {"id": str(subject_key_id)},
    )
    if result.rowcount == 0:
        # Either the row doesn't exist or it's already destroyed.
        exists = session.execute(
            text(
                "SELECT destroyed_at FROM subject_key "
                "WHERE id = CAST(:id AS UUID)"
            ),
            {"id": str(subject_key_id)},
        ).scalar_one_or_none()
        if exists is None:
            raise KeyError(subject_key_id)
        # already destroyed — idempotent no-op.
