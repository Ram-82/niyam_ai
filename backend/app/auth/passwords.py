"""Password hashing + policy enforcement.

Policy:
* bcrypt via passlib (already in deps).
* Minimum 12 characters AND zxcvbn score >= 3.
* zxcvbn is language-aware enough to reject "password123456" (predictable
  even though it's 14 characters) — that's precisely the case the length
  rule alone misses.

The bcrypt cost stays at passlib's default (12 rounds as of 1.7.4). This
gives ~250ms verify times on modest hardware, which is the ballpark we
want for password verification anyway.
"""
from __future__ import annotations

from passlib.context import CryptContext
from zxcvbn import zxcvbn


class WeakPasswordError(ValueError):
    """Raised by ``assert_password_strength`` when policy is not met."""


MIN_LENGTH = 12
MIN_ZXCVBN_SCORE = 3


_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(pw: str) -> str:
    """Return a bcrypt hash suitable for storage in ``app_user.password_hash``."""
    return _pwd_context.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    """Constant-ish-time bcrypt verify. Returns False on any failure."""
    try:
        return _pwd_context.verify(pw, hashed)
    except (ValueError, TypeError):
        # Malformed hash — treat as a failed verification, do not raise.
        return False


def assert_password_strength(pw: str) -> None:
    """Raise ``WeakPasswordError`` if policy is not met.

    Enforces BOTH minimum length AND zxcvbn score. Length alone lets long
    but predictable passwords through; zxcvbn alone would accept an 8-char
    string with high entropy.
    """
    if len(pw) < MIN_LENGTH:
        raise WeakPasswordError(
            f"password must be at least {MIN_LENGTH} characters"
        )
    score = zxcvbn(pw).get("score", 0)
    if score < MIN_ZXCVBN_SCORE:
        raise WeakPasswordError(
            f"password is too predictable (zxcvbn score {score} < "
            f"{MIN_ZXCVBN_SCORE})"
        )
