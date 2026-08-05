"""MockGSPAdapter — GSPClient over HTTP to app/gsp/mock_server.py.

This is the ONLY module the mock-server URL should appear in beyond
config. When a real vendor lands, ``CygnetAdapter`` / ``IRISAdapter``
etc. live alongside this file — each translating vendor-native error
codes into our ``GSPError`` taxonomy the same way this one does.

Stateless. No DB access. No logging of tokens or OTPs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx

from app.gsp.client import (
    ConsentRequest,
    ConsentRevoked,
    GSPClient,
    GSTNUnavailable,
    OTPExpired,
    OTPInvalid,
    RateLimited,
    Session,
    SessionExpired,
    UnknownGSPError,
)


def _parse_dt(s: str) -> datetime:
    """Parse the mock server's ISO strings. Naive-strip the tzinfo so we
    stay compatible with :attr:`Session.is_expired` which uses
    ``datetime.utcnow()``."""
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(tz=None).replace(tzinfo=None)
    return dt


def _translate(resp: httpx.Response) -> None:
    """Map vendor HTTP failure to our taxonomy. No-op on 2xx."""
    if resp.is_success:
        return
    try:
        body = resp.json()
    except Exception:
        body = {}
    detail = body.get("detail") if isinstance(body, dict) else {}
    if not isinstance(detail, dict):
        detail = {"raw": detail}
    code = str(detail.get("vendor_code") or "")
    message = str(detail.get("message") or resp.reason_phrase or "GSP error")
    retry_after = None
    ra = resp.headers.get("Retry-After")
    if ra and ra.isdigit():
        retry_after = int(ra)

    kwargs: dict[str, Any] = {
        "http_status": resp.status_code,
        "vendor_code": code or None,
        "detail": detail,
    }
    if retry_after is not None:
        kwargs["retry_after_seconds"] = retry_after

    if code in ("OTP_MISMATCH",):
        raise OTPInvalid(message, **kwargs)
    if code in ("OTP_EXPIRED",):
        raise OTPExpired(message, **kwargs)
    if code in ("SESSION_EXPIRED", "SESSION_UNKNOWN"):
        raise SessionExpired(message, **kwargs)
    if code in ("GSTN_UNAVAILABLE",):
        raise GSTNUnavailable(message, **kwargs)
    if code in ("RATE_LIMIT",) or resp.status_code == 429:
        raise RateLimited(message, **kwargs)
    if code in ("CONSENT_REVOKED",):
        raise ConsentRevoked(message, **kwargs)
    # 5xx without a known code → GSTN-side; retryable.
    if 500 <= resp.status_code < 600:
        raise GSTNUnavailable(message, **kwargs)
    raise UnknownGSPError(message, **kwargs)


class MockGSPAdapter(GSPClient):
    """HTTP client for the local MockGSPServer."""

    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self._base_url, timeout=self._timeout)

    def initiate_consent(self, gstin: str) -> ConsentRequest:
        with self._client() as c:
            resp = c.post("/gsp/v1/consent", json={"gstin": gstin})
        _translate(resp)
        body = resp.json()
        return ConsentRequest(
            gstin=gstin,
            request_id=body["request_id"],
            expires_at=_parse_dt(body["expires_at"]),
            vendor_context={},  # mock has nothing extra to round-trip
        )

    def confirm_consent(
        self, consent_request: ConsentRequest, otp: str
    ) -> Session:
        with self._client() as c:
            resp = c.post(
                "/gsp/v1/consent/confirm",
                json={"request_id": consent_request.request_id, "otp": otp},
            )
        _translate(resp)
        body = resp.json()
        return Session(
            gstin=consent_request.gstin,
            token=body["token"],
            issued_at=_parse_dt(body["issued_at"]),
            expires_at=_parse_dt(body["expires_at"]),
            vendor_context={},
        )

    def fetch_gstr2b(
        self, session: Session, gstin: str, period: str
    ) -> dict[str, Any]:
        with self._client() as c:
            resp = c.post(
                "/gsp/v1/gstr2b",
                json={"token": session.token, "gstin": gstin, "period": period},
            )
        _translate(resp)
        return resp.json()

    def session_status(self, session: Session) -> bool:
        with self._client() as c:
            resp = c.post(
                "/gsp/v1/session/status", json={"token": session.token}
            )
        _translate(resp)
        return bool(resp.json().get("live"))

    def refresh_or_reauth(self, session: Session) -> Session | None:
        with self._client() as c:
            resp = c.post(
                "/gsp/v1/session/refresh", json={"token": session.token}
            )
        _translate(resp)
        body = resp.json()
        if not body.get("token"):
            return None
        return Session(
            gstin=session.gstin,
            token=body["token"],
            issued_at=_parse_dt(body["issued_at"]),
            expires_at=_parse_dt(body["expires_at"]),
            vendor_context=session.vendor_context,
        )
