"""Redis-backed brute-force lockout for GSP consent OTP submissions.

Mirrors ``app/auth/lockout.py`` but keyed by ``(user_id, gstin)`` so a
CA trying wrong OTPs on one client's connection cannot lock out another
client — and a compromised token cannot lock out a legitimate user
across all their GSTINs.

Same policy as login: 5 failures per 15 minutes → 15-minute lockout.
Same audit expectation: the API layer emits an ``audit_log`` row with
``action='gsp.otp_lockout'`` on the transition to locked. The OTP
itself is NEVER included in the audit metadata.
"""
from __future__ import annotations

import redis

from app.config import settings


MAX_ATTEMPTS = 5
WINDOW_SECONDS = 900


_redis: redis.Redis = redis.Redis.from_url(
    settings.redis_url, decode_responses=True
)


def _norm(gstin: str) -> str:
    return gstin.strip().upper()


def _attempts_key(user_id: str, gstin: str) -> str:
    return f"gsp_otp_attempts:{user_id}:{_norm(gstin)}"


def _locked_key(user_id: str, gstin: str) -> str:
    return f"gsp_otp_locked:{user_id}:{_norm(gstin)}"


def is_locked(user_id: str, gstin: str) -> bool:
    return _redis.exists(_locked_key(user_id, gstin)) == 1


def record_failure(user_id: str, gstin: str) -> int:
    key = _attempts_key(user_id, gstin)
    count = int(_redis.incr(key))
    if count == 1:
        _redis.expire(key, WINDOW_SECONDS)
    if count >= MAX_ATTEMPTS:
        _redis.set(_locked_key(user_id, gstin), "1", ex=WINDOW_SECONDS)
    return count


def clear(user_id: str, gstin: str) -> None:
    _redis.delete(_attempts_key(user_id, gstin), _locked_key(user_id, gstin))


def ttl_seconds(user_id: str, gstin: str) -> int:
    ttl = _redis.ttl(_locked_key(user_id, gstin))
    return ttl if ttl >= 0 else -1


# ---------------------------------------------------------------------------
# Per-GSTIN initiate_consent cooldown (SMS-flood block).
#
# The confirm-side per-(user, gstin) lockout stops brute-force guessing but
# does NOT stop an attacker with a valid session from calling
# initiate_consent repeatedly, which triggers a fresh SMS to the MSME
# owner's phone each time. That is user-hostile even if no login is
# compromised. So: cap initiate_consent to 3 per hour PER GSTIN (not
# per user — the phone doesn't care which staff account did the flooding).
#
# Returns "cooldown active, retry in X" instead of hitting the vendor.
# ---------------------------------------------------------------------------


INITIATE_MAX_PER_HOUR = 3
INITIATE_WINDOW_SECONDS = 3600


def _initiate_key(gstin: str) -> str:
    return f"gsp_initiate:{_norm(gstin)}"


def initiate_cooldown_ttl(gstin: str) -> int:
    """Seconds until the cooldown lifts, or -1 if no cooldown is active."""
    ttl = _redis.ttl(_initiate_key(gstin))
    return ttl if ttl > 0 else -1


def try_reserve_initiate(gstin: str) -> tuple[bool, int]:
    """Try to reserve one initiate_consent slot for ``gstin``.

    Returns (reserved, retry_after_seconds). ``retry_after_seconds`` is
    the TTL of the current window when reserved=False, else 0.

    Increments a counter with a 1h TTL on first hit. Once the counter
    reaches INITIATE_MAX_PER_HOUR, further calls fail until the window
    rolls off. Counter is per-GSTIN because that's what the SMS goes to.
    """
    key = _initiate_key(gstin)
    count = int(_redis.incr(key))
    if count == 1:
        _redis.expire(key, INITIATE_WINDOW_SECONDS)
    if count > INITIATE_MAX_PER_HOUR:
        # Roll back the over-increment so a subsequent legitimate window
        # opens with count=1 again. We can't atomically test-and-set in a
        # single command without a Lua script; the DECR is safe because
        # the guarded write hasn't happened.
        _redis.decr(key)
        ttl = _redis.ttl(key)
        return False, max(1, ttl)
    return True, 0


# NOTE: A test-only cooldown-clear helper used to live here. It was moved
# to ``tests/support/lockout_admin.py`` in P2.1 Stage C so it cannot ship
# in a deployed process. The adversarial test in
# ``tests/security/test_no_test_helpers_in_app.py`` fails if it ever
# comes back. There is no product need to clear this window.
