"""Sliding-window rate limiter — unit-level correctness.

Endpoint wiring is covered by tests/integration/test_auth_rate_limit.py.
"""
from __future__ import annotations

import time

import pytest

from app.auth import rate_limit


@pytest.fixture(autouse=True)
def _cleanup():
    # Tests share the Redis instance; wipe every rl:* key between cases.
    rate_limit._redis.eval(
        "for _, k in ipairs(redis.call('keys', ARGV[1])) do redis.call('del', k) end; return 0",
        0,
        "rl:*",
    )
    yield


def test_allowed_below_limit() -> None:
    for i in range(rate_limit.POLICIES["login_email"].max_hits):
        allowed, retry = rate_limit.check("login_email", f"u{i}@ex.com")
        assert allowed
        assert retry == 0


def test_denied_when_burst_exceeds_limit() -> None:
    for _ in range(rate_limit.POLICIES["login_email"].max_hits):
        rate_limit.check("login_email", "burst@example.com")
    allowed, retry = rate_limit.check("login_email", "burst@example.com")
    assert not allowed
    assert retry >= 1


def test_case_insensitive_bucket() -> None:
    for _ in range(rate_limit.POLICIES["login_email"].max_hits):
        rate_limit.check("login_email", "Alice@Example.com")
    # Same email in a different case must share the bucket, else the
    # limiter is trivially bypassed by casing tricks.
    allowed, _ = rate_limit.check("login_email", "alice@example.com")
    assert not allowed


def test_scopes_are_independent() -> None:
    for _ in range(rate_limit.POLICIES["login_ip"].max_hits):
        rate_limit.check("login_ip", "1.2.3.4")
    # Same identifier under a different scope must be untouched.
    allowed, _ = rate_limit.check("login_email", "1.2.3.4")
    assert allowed


def test_reset_clears_bucket() -> None:
    for _ in range(rate_limit.POLICIES["login_email"].max_hits):
        rate_limit.check("login_email", "wipe@example.com")
    assert rate_limit.check("login_email", "wipe@example.com")[0] is False
    rate_limit.reset("login_email", "wipe@example.com")
    assert rate_limit.check("login_email", "wipe@example.com")[0] is True
