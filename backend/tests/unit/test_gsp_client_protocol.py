"""Unit tests for the vendor-agnostic GSPClient protocol shape.

The protocol is what real vendor adapters (CygnetAdapter, IRISAdapter…)
will conform to. We test it here so a rename or signature drift breaks
in unit tests, not at vendor-integration time.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest

from app.gsp.client import (
    ConsentRequest,
    ConsentRevoked,
    GSPClient,
    GSPError,
    GSPErrorKind,
    GSTNUnavailable,
    OTPExpired,
    OTPInvalid,
    RateLimited,
    Session,
    SessionExpired,
    UnknownGSPError,
)


class _StubAdapter:
    """A minimal adapter that satisfies the Protocol structurally."""

    def initiate_consent(self, gstin: str) -> ConsentRequest:
        return ConsentRequest(
            gstin=gstin,
            request_id="stub",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )

    def confirm_consent(
        self, consent_request: ConsentRequest, otp: str
    ) -> Session:
        now = datetime.utcnow()
        return Session(
            gstin=consent_request.gstin,
            token="stub-token",
            issued_at=now,
            expires_at=now + timedelta(minutes=30),
        )

    def fetch_gstr2b(
        self, session: Session, gstin: str, period: str
    ) -> dict[str, Any]:
        return {"data": {"rtnprd": period}}

    def session_status(self, session: Session) -> bool:
        return not session.is_expired

    def refresh_or_reauth(self, session: Session) -> Session | None:
        return session


def test_stub_adapter_satisfies_protocol_runtime_check() -> None:
    assert isinstance(_StubAdapter(), GSPClient)


def test_session_is_expired_flag() -> None:
    past = datetime.utcnow() - timedelta(seconds=1)
    future = datetime.utcnow() + timedelta(seconds=60)
    assert Session(
        gstin="X", token="t", issued_at=past, expires_at=past
    ).is_expired is True
    assert Session(
        gstin="X", token="t", issued_at=past, expires_at=future
    ).is_expired is False


@pytest.mark.parametrize(
    "exc_cls, kind",
    [
        (OTPInvalid, GSPErrorKind.OTP_INVALID),
        (OTPExpired, GSPErrorKind.OTP_EXPIRED),
        (SessionExpired, GSPErrorKind.SESSION_EXPIRED),
        (GSTNUnavailable, GSPErrorKind.GSTN_UNAVAILABLE),
        (RateLimited, GSPErrorKind.RATE_LIMITED),
        (ConsentRevoked, GSPErrorKind.CONSENT_REVOKED),
        (UnknownGSPError, GSPErrorKind.UNKNOWN),
    ],
)
def test_every_taxonomy_entry_has_a_dedicated_exception(exc_cls, kind) -> None:
    e = exc_cls("boom", http_status=500, retry_after_seconds=1, vendor_code="X")
    assert isinstance(e, GSPError)
    assert e.kind == kind
    assert e.http_status == 500
    assert e.retry_after_seconds == 1
    assert e.vendor_code == "X"
