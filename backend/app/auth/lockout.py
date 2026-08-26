"""Redis-backed brute-force lockout keyed by email.

Design notes:

* Keyed by email (case-insensitive; normalized to lowercase) rather than
  ``user_id`` because we must handle the "email does not exist" case too
  — otherwise the response time diverges and we leak account enumeration.
* Two keys per email:
    - ``login_attempts:<email>`` — count with TTL = WINDOW_SECONDS.
    - ``locked_until:<email>``   — presence indicates lockout in effect.
* ``record_failure`` increments and, on the MAX_ATTEMPTS-th failure, sets
  the ``locked_until`` marker. Returns the post-increment count so the API
  layer can emit an audit_log row on the transition to locked.
"""
from __future__ import annotations

import redis

from app.config import settings


MAX_ATTEMPTS = 5
WINDOW_SECONDS = 900  # 15 minutes for both the counter and the lockout


_redis: redis.Redis = redis.Redis.from_url(
    settings.redis_url, decode_responses=True
)


def _normalize(email: str) -> str:
    return email.strip().lower()


def _attempts_key(email: str) -> str:
    return f"login_attempts:{_normalize(email)}"


def _locked_key(email: str) -> str:
    return f"locked_until:{_normalize(email)}"


def is_locked(email: str) -> bool:
    return _redis.exists(_locked_key(email)) == 1


def record_failure(email: str) -> int:
    """Increment the failure counter. Return the new count.

    On the MAX_ATTEMPTS-th failure, set the ``locked_until`` marker. Both
    keys share the same TTL — after the window they roll off together.
    """
    from app.observability import metrics

    key = _attempts_key(email)
    # INCR + EXPIRE on first hit. Redis auto-creates the key at value 1.
    count = int(_redis.incr(key))
    if count == 1:
        _redis.expire(key, WINDOW_SECONDS)
    metrics.auth_failures_total.labels(reason="login").inc()
    if count >= MAX_ATTEMPTS:
        # Only transition-into-locked increments the lockout counter;
        # subsequent failures inside the window keep the marker but
        # do NOT double-count the transition.
        was_locked = _redis.exists(_locked_key(email)) == 1
        _redis.set(_locked_key(email), "1", ex=WINDOW_SECONDS)
        if not was_locked:
            metrics.auth_lockouts_total.inc()
    return count


def clear(email: str) -> None:
    """Clear both counter and lockout marker (called on successful login)."""
    _redis.delete(_attempts_key(email), _locked_key(email))


def ttl_seconds(email: str) -> int:
    """Seconds until the current lockout expires. -1 if not locked."""
    ttl = _redis.ttl(_locked_key(email))
    # redis-py returns -2 if missing, -1 if no TTL. Both mean "not locked".
    return ttl if ttl >= 0 else -1
