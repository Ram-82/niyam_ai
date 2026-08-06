"""Redis-backed sliding-window rate limiter.

Uses ZSET with unix-timestamp scores as the sliding window: on each
check we drop entries older than the window, count what's left, and
add the current timestamp. Cheap (three commands, all O(log N)) and
gives an exact window rather than the fixed-bucket approximation of
INCR+EXPIRE.

Two policies wired up by the auth endpoints:

* ``login``    — 10 req / 60s per IP, 5 req / 60s per email.
* ``register`` — 5 req / 3600s per IP.

The middleware layer is deliberately unopinionated: callers ask
``check(scope, key)`` and receive ``(allowed, retry_after_seconds)``.
The endpoint decides whether to 429 and what to log.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

import redis

from app.config import settings


_redis: redis.Redis = redis.Redis.from_url(
    settings.redis_url, decode_responses=True
)


@dataclass(frozen=True)
class Policy:
    """One rate-limit rule. ``max_hits`` in the last ``window_s`` seconds."""

    name: str
    max_hits: int
    window_s: int


POLICIES: dict[str, Policy] = {
    "login_ip":       Policy("login_ip",       max_hits=10, window_s=60),
    "login_email":    Policy("login_email",    max_hits=5,  window_s=60),
    "register_ip":    Policy("register_ip",    max_hits=5,  window_s=3600),
    # Password reset emails are expensive (real SMTP send) and useful
    # for enumeration probes if unlimited. 3/hour per email, 5/hour per
    # IP — tight because the legitimate use case is once a month.
    "forgot_email":   Policy("forgot_email",   max_hits=3,  window_s=3600),
    "forgot_ip":      Policy("forgot_ip",      max_hits=5,  window_s=3600),
}


def _key(policy_name: str, identifier: str) -> str:
    # Lower-case the identifier so "Alice@X" and "alice@x" share a bucket.
    return f"rl:{policy_name}:{identifier.lower()}"


def check(policy_name: str, identifier: str) -> tuple[bool, int]:
    """Return (allowed, retry_after_seconds).

    ``retry_after_seconds`` is 0 when allowed; otherwise the number of
    seconds until the oldest still-in-window entry rolls off. Callers
    surface it as the ``Retry-After`` HTTP header.
    """
    policy = POLICIES[policy_name]
    now_ms = int(time.time() * 1000)
    window_ms = policy.window_s * 1000
    cutoff = now_ms - window_ms
    key = _key(policy_name, identifier)

    pipe = _redis.pipeline()
    pipe.zremrangebyscore(key, "-inf", cutoff)
    pipe.zcard(key)
    _, count = pipe.execute()

    if count >= policy.max_hits:
        # Retry-After = seconds until the oldest entry falls out of the
        # window. ZRANGE returns the smallest score first.
        oldest = _redis.zrange(key, 0, 0, withscores=True)
        if not oldest:
            return True, 0  # race — window emptied between commands
        oldest_ms = int(oldest[0][1])
        retry_after = max(1, int((oldest_ms + window_ms - now_ms) / 1000) + 1)
        return False, retry_after

    # Record this hit. Member is a unique random id so identical-timestamp
    # hits don't collapse into one ZSET entry.
    member = f"{now_ms}:{uuid.uuid4().hex[:8]}"
    pipe = _redis.pipeline()
    pipe.zadd(key, {member: now_ms})
    pipe.expire(key, policy.window_s + 5)  # +5s safety so tail entries can decay
    pipe.execute()
    return True, 0


def reset(policy_name: str, identifier: str) -> None:
    """Test-only helper — clears the bucket for one (scope, id) pair."""
    _redis.delete(_key(policy_name, identifier))
