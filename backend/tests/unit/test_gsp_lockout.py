"""Unit tests for the per-(user, gstin) OTP lockout."""
from __future__ import annotations

import uuid

from app.gsp import lockout


def test_lockout_after_five_failures() -> None:
    uid = str(uuid.uuid4())
    gstin = "29AAAAA0000A1Z5"
    for i in range(1, 5):
        n = lockout.record_failure(uid, gstin)
        assert n == i
        assert not lockout.is_locked(uid, gstin)
    n = lockout.record_failure(uid, gstin)
    assert n == 5
    assert lockout.is_locked(uid, gstin)


def test_clear_resets_state() -> None:
    uid = str(uuid.uuid4())
    gstin = "29AAAAA0000A1Z5"
    for _ in range(5):
        lockout.record_failure(uid, gstin)
    assert lockout.is_locked(uid, gstin)
    lockout.clear(uid, gstin)
    assert not lockout.is_locked(uid, gstin)
    assert lockout.record_failure(uid, gstin) == 1


def test_lockout_is_per_user_and_per_gstin() -> None:
    """Lockout on one (user, gstin) must not affect another."""
    u1, u2 = str(uuid.uuid4()), str(uuid.uuid4())
    g1, g2 = "29AAAAA0000A1Z5", "27BBBBB1111B2Z6"
    for _ in range(5):
        lockout.record_failure(u1, g1)
    assert lockout.is_locked(u1, g1)
    # Same user, different GSTIN: unaffected.
    assert not lockout.is_locked(u1, g2)
    # Different user, same GSTIN: unaffected.
    assert not lockout.is_locked(u2, g1)


def test_gstin_normalization_case_insensitive() -> None:
    uid = str(uuid.uuid4())
    for _ in range(5):
        lockout.record_failure(uid, "29aaaaa0000a1z5")
    assert lockout.is_locked(uid, "29AAAAA0000A1Z5")
    assert lockout.is_locked(uid, "29aaaaa0000a1z5")
