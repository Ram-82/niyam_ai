"""Redis-backed JTI revocation set.

Semantics:

* Every revoked JTI gets a key ``revoked:refresh:<jti>`` (or
  ``revoked:totp_setup:<jti>``) with TTL equal to the token's remaining
  lifetime. Once the token would have expired anyway the key evaporates and
  we do not grow the set forever.
* Access tokens are stateless: their JTI is only added on explicit /logout
  and only for the remaining access lifetime (<= 15 min).
"""
from __future__ import annotations

import redis

from app.config import settings


_redis: redis.Redis = redis.Redis.from_url(
    settings.redis_url, decode_responses=True
)


def _key(jti: str) -> str:
    return f"revoked:jti:{jti}"


def revoke(jti: str, ttl_seconds: int) -> None:
    """Mark ``jti`` revoked for ``ttl_seconds``. No-op if ttl <= 0."""
    if ttl_seconds <= 0:
        return
    _redis.set(_key(jti), "1", ex=ttl_seconds)


def is_revoked(jti: str) -> bool:
    return _redis.exists(_key(jti)) == 1
