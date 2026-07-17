"""TOTP helpers around pyotp.

Every user is required to enroll TOTP on first login. The setup flow is:

1. Client POSTs valid password on an unconfirmed user.
2. Server generates a fresh base32 secret, stores it in
   ``app_user.totp_secret``, and returns a ``otpauth://`` URI.
3. Client scans the URI into Google Authenticator / Authy / 1Password.
4. Client POSTs the first 6-digit code to /auth/totp/verify.
5. On successful verify, ``totp_confirmed`` flips to true and the client
   gets a real access + refresh token pair.
"""
from __future__ import annotations

import pyotp


def generate_secret() -> str:
    """Return a fresh base32-encoded TOTP secret (160 bits)."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str, issuer: str = "Niyam AI") -> str:
    """Build an ``otpauth://totp/...`` URI that authenticator apps can scan."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def verify_totp(secret: str, code: str, valid_window: int = 1) -> bool:
    """Return True if ``code`` is a valid TOTP for ``secret``.

    ``valid_window=1`` accepts codes from the current, previous, and next
    30-second window — this covers modest clock skew between the client and
    server without materially widening the attack surface.
    """
    if not secret or not code:
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=valid_window)
    except (TypeError, ValueError):
        return False
