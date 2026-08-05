"""Unit tests for the per-GSTIN initiate_consent cooldown (SMS-flood block)."""
from __future__ import annotations

from app.gsp import lockout


GSTIN = "29AAAAA0000A1Z5"


def test_first_three_reservations_succeed_fourth_blocks() -> None:
    for i in range(lockout.INITIATE_MAX_PER_HOUR):
        ok, retry_after = lockout.try_reserve_initiate(GSTIN)
        assert ok, f"attempt {i + 1} should be reserved"
        assert retry_after == 0
    ok, retry_after = lockout.try_reserve_initiate(GSTIN)
    assert not ok
    assert 0 < retry_after <= lockout.INITIATE_WINDOW_SECONDS


def test_cooldown_ttl_visible_after_lockout() -> None:
    for _ in range(lockout.INITIATE_MAX_PER_HOUR):
        lockout.try_reserve_initiate(GSTIN)
    lockout.try_reserve_initiate(GSTIN)  # over-attempt
    ttl = lockout.initiate_cooldown_ttl(GSTIN)
    assert ttl > 0


def test_cooldown_is_per_gstin() -> None:
    other = "27BBBBB1111B2Z6"
    for _ in range(lockout.INITIATE_MAX_PER_HOUR):
        lockout.try_reserve_initiate(GSTIN)
    lockout.try_reserve_initiate(GSTIN)  # blocked
    # Different GSTIN is unaffected.
    ok, _ = lockout.try_reserve_initiate(other)
    assert ok
