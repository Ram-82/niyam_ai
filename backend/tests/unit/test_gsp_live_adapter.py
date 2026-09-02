"""Unit tests for LiveGSPAdapter.

httpx.MockTransport lets us assert on the exact URL, method, headers,
and body sent by the adapter without spinning up a fake HTTP server.
That makes these tests hermetic and independent of any real vendor
credentials.

Load-bearing properties:

* Every call carries ``X-Api-Key: <key>``.
* URLs are built as ``<path_prefix>/<vendor-endpoint>`` — bumping the
  vendor's API version is a single env change (``GSP_LIVE_PATH_PREFIX``).
* Vendor error codes map into the correct GSPError subclass; 429 with
  no body still raises RateLimited; 5xx with no body still raises
  GSTNUnavailable.
* ``vendor_context`` is round-tripped from initiate → confirm → refresh
  so a vendor that needs a refresh_token can silently re-authenticate.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
import pytest

from app.gsp.adapter_live import LiveGSPAdapter
from app.gsp.client import (
    ConsentRequest,
    ConsentRevoked,
    GSTNUnavailable,
    OTPExpired,
    OTPInvalid,
    RateLimited,
    Session,
    SessionExpired,
    UnknownGSPError,
)


BASE_URL = "https://sandbox.mastergst.example"
API_KEY = "test-api-key-01"
PATH_PREFIX = "/api/v0.4"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter(handler) -> LiveGSPAdapter:
    """Wire an adapter around a MockTransport with the given handler."""
    return LiveGSPAdapter(
        base_url=BASE_URL,
        api_key=API_KEY,
        path_prefix=PATH_PREFIX,
        transport=httpx.MockTransport(handler),
    )


def _json_resp(status: int, body: dict[str, Any], headers: Optional[dict] = None) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
    )


# ---------------------------------------------------------------------------
# Header + URL wiring
# ---------------------------------------------------------------------------


class TestHeaderAndUrlWiring:
    def test_api_key_header_attached_to_initiate_consent(self) -> None:
        captured: dict[str, Any] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["url"] = str(req.url)
            captured["method"] = req.method
            captured["api_key"] = req.headers.get("X-Api-Key")
            captured["content_type"] = req.headers.get("Content-Type")
            return _json_resp(200, {"request_id": "REQ-1", "expires_at": "2026-08-11T10:00:00Z"})

        adapter = _make_adapter(handler)
        adapter.initiate_consent("29ABCDE1234F1ZW")

        assert captured["api_key"] == API_KEY
        assert captured["content_type"] == "application/json"
        assert captured["method"] == "POST"
        assert captured["url"].endswith("/api/v0.4/gstr2b/otp/29ABCDE1234F1ZW")

    def test_fetch_gstr2b_sends_bearer_token_and_uses_get(self) -> None:
        captured: dict[str, Any] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["method"] = req.method
            captured["url"] = str(req.url)
            captured["auth"] = req.headers.get("Authorization")
            captured["x_auth"] = req.headers.get("X-Auth-Token")
            return _json_resp(200, {"data": {"b2b": []}})

        adapter = _make_adapter(handler)
        session = Session(
            gstin="29ABCDE1234F1ZW",
            token="session-tok-42",
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        adapter.fetch_gstr2b(session, "29ABCDE1234F1ZW", "202607")

        assert captured["method"] == "GET"
        assert captured["url"].endswith("/api/v0.4/gstr2b/29ABCDE1234F1ZW/202607")
        # Both auth header shapes sent — vendor picks whichever it honors.
        assert captured["auth"] == "Bearer session-tok-42"
        assert captured["x_auth"] == "session-tok-42"

    def test_confirm_consent_posts_otp_and_request_id(self) -> None:
        captured: dict[str, Any] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["url"] = str(req.url)
            captured["body"] = json.loads(req.content)
            return _json_resp(
                200,
                {
                    "token": "TOK-9",
                    "issued_at": "2026-08-11T10:00:00Z",
                    "expires_at": "2026-08-11T16:00:00Z",
                },
            )

        adapter = _make_adapter(handler)
        req = ConsentRequest(
            gstin="29ABCDE1234F1ZW",
            request_id="REQ-1",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
            vendor_context={"txn": "T-abc"},
        )
        session = adapter.confirm_consent(req, otp="123456")

        assert captured["url"].endswith(
            "/api/v0.4/gstr2b/otp/29ABCDE1234F1ZW/verify"
        )
        assert captured["body"]["otp"] == "123456"
        assert captured["body"]["request_id"] == "REQ-1"
        # vendor_context contents round-trip into the verify payload.
        assert captured["body"]["txn"] == "T-abc"
        assert session.token == "TOK-9"
        assert session.gstin == "29ABCDE1234F1ZW"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestFullConsentAndFetchFlow:
    def test_end_to_end_returns_json_body(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            path = req.url.path
            if path.endswith("/otp/29ABCDE1234F1ZW"):
                return _json_resp(200, {
                    "request_id": "REQ-99",
                    "expires_at": "2026-08-11T10:05:00Z",
                    "txn": "T-1",
                })
            if path.endswith("/otp/29ABCDE1234F1ZW/verify"):
                return _json_resp(200, {
                    "token": "SESS-99",
                    "issued_at": "2026-08-11T10:05:30Z",
                    "expires_at": "2026-08-11T16:05:30Z",
                    "refresh_token": "REF-abc",
                })
            if path.endswith("/gstr2b/29ABCDE1234F1ZW/202607"):
                return _json_resp(200, {"data": {"b2b": [{"ctin": "27XYZAB1234Q1Z5"}]}})
            return _json_resp(404, {"error_cd": "NOT_FOUND", "message": path})

        adapter = _make_adapter(handler)
        req = adapter.initiate_consent("29ABCDE1234F1ZW")
        # Vendor context captured for the confirm round-trip.
        assert req.vendor_context.get("txn") == "T-1"

        session = adapter.confirm_consent(req, otp="123456")
        # refresh_token got captured for later refresh_or_reauth.
        assert session.vendor_context.get("refresh_token") == "REF-abc"

        body = adapter.fetch_gstr2b(session, "29ABCDE1234F1ZW", "202607")
        assert body["data"]["b2b"][0]["ctin"] == "27XYZAB1234Q1Z5"


# ---------------------------------------------------------------------------
# Error-code mapping
# ---------------------------------------------------------------------------


class TestErrorTranslation:
    @pytest.mark.parametrize(
        "status,body,expected_exc",
        [
            (400, {"error_cd": "OTP_MISMATCH", "message": "bad OTP"}, OTPInvalid),
            (400, {"error_cd": "OTP_EXPIRED", "message": "expired"}, OTPExpired),
            (401, {"error_cd": "SESSION_EXPIRED", "message": "reauth"}, SessionExpired),
            (401, {"error_cd": "AUTH_TOKEN_EXPIRED"}, SessionExpired),
            (403, {"error_cd": "CONSENT_REVOKED"}, ConsentRevoked),
            (429, {"error_cd": "RATE_LIMIT", "message": "slow down"}, RateLimited),
            (503, {"error_cd": "GSTN_UNAVAILABLE"}, GSTNUnavailable),
        ],
    )
    def test_vendor_code_maps_to_typed_error(
        self, status: int, body: dict, expected_exc: type,
    ) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return _json_resp(status, body)

        adapter = _make_adapter(handler)
        with pytest.raises(expected_exc) as excinfo:
            adapter.initiate_consent("29ABCDE1234F1ZW")
        assert excinfo.value.http_status == status

    def test_429_without_body_still_rate_limited(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(429, headers={"Retry-After": "60"})

        adapter = _make_adapter(handler)
        with pytest.raises(RateLimited) as excinfo:
            adapter.initiate_consent("29ABCDE1234F1ZW")
        assert excinfo.value.retry_after_seconds == 60

    def test_5xx_without_body_maps_to_gstn_unavailable(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(502)

        adapter = _make_adapter(handler)
        with pytest.raises(GSTNUnavailable):
            adapter.initiate_consent("29ABCDE1234F1ZW")

    def test_401_without_body_maps_to_session_expired(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(401)

        adapter = _make_adapter(handler)
        session = Session(
            gstin="29ABCDE1234F1ZW",
            token="expired-tok",
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        with pytest.raises(SessionExpired):
            adapter.fetch_gstr2b(session, "29ABCDE1234F1ZW", "202607")

    def test_unknown_error_code_maps_to_unknown(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return _json_resp(400, {"error_cd": "MYSTERY_CODE_42"})

        adapter = _make_adapter(handler)
        with pytest.raises(UnknownGSPError) as excinfo:
            adapter.initiate_consent("29ABCDE1234F1ZW")
        assert excinfo.value.vendor_code == "MYSTERY_CODE_42"


# ---------------------------------------------------------------------------
# Response-shape defensiveness
# ---------------------------------------------------------------------------


class TestResponseShapeDefensiveness:
    def test_initiate_without_request_id_raises_unknown(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return _json_resp(200, {"expires_at": "2026-08-11T10:00:00Z"})

        adapter = _make_adapter(handler)
        with pytest.raises(UnknownGSPError, match="request_id"):
            adapter.initiate_consent("29ABCDE1234F1ZW")

    def test_confirm_without_token_raises_unknown(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return _json_resp(200, {"issued_at": "2026-08-11T10:00:00Z"})

        adapter = _make_adapter(handler)
        req = ConsentRequest(
            gstin="29ABCDE1234F1ZW",
            request_id="REQ-1",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        with pytest.raises(UnknownGSPError, match="token"):
            adapter.confirm_consent(req, otp="123456")

    def test_initiate_omitting_expires_at_defaults_to_5_minutes(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return _json_resp(200, {"request_id": "REQ-1"})

        adapter = _make_adapter(handler)
        before = datetime.utcnow()
        req = adapter.initiate_consent("29ABCDE1234F1ZW")
        delta = (req.expires_at - before).total_seconds()
        # Default TTL is 300 seconds; allow ±5 seconds for wall-clock jitter.
        assert 295 <= delta <= 305


# ---------------------------------------------------------------------------
# Session refresh
# ---------------------------------------------------------------------------


class TestRefreshOrReauth:
    def test_no_refresh_token_returns_none(self) -> None:
        adapter = _make_adapter(lambda req: httpx.Response(500))  # never called
        session = Session(
            gstin="29ABCDE1234F1ZW",
            token="stale",
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow(),
            vendor_context={},  # no refresh token
        )
        assert adapter.refresh_or_reauth(session) is None

    def test_refresh_success_returns_new_session(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            assert req.url.path.endswith("/session/refresh")
            assert json.loads(req.content)["refresh_token"] == "REF-abc"
            return _json_resp(200, {
                "token": "NEW-TOK",
                "issued_at": "2026-08-11T16:00:00Z",
                "expires_at": "2026-08-11T22:00:00Z",
            })

        adapter = _make_adapter(handler)
        session = Session(
            gstin="29ABCDE1234F1ZW",
            token="old-tok",
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow(),
            vendor_context={"refresh_token": "REF-abc"},
        )
        new_session = adapter.refresh_or_reauth(session)
        assert new_session is not None
        assert new_session.token == "NEW-TOK"

    def test_refresh_endpoint_401_raises_session_expired(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return _json_resp(401, {"error_cd": "AUTH_TOKEN_EXPIRED"})

        adapter = _make_adapter(handler)
        session = Session(
            gstin="29ABCDE1234F1ZW",
            token="old-tok",
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow(),
            vendor_context={"refresh_token": "REF-abc"},
        )
        with pytest.raises(SessionExpired):
            adapter.refresh_or_reauth(session)


# ---------------------------------------------------------------------------
# session_status
# ---------------------------------------------------------------------------


class TestSessionStatus:
    def test_returns_true_for_unexpired_session(self) -> None:
        adapter = _make_adapter(lambda req: httpx.Response(500))
        s = Session(
            gstin="29ABCDE1234F1ZW",
            token="tok",
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(hours=1),
        )
        assert adapter.session_status(s) is True

    def test_returns_false_for_expired_session(self) -> None:
        adapter = _make_adapter(lambda req: httpx.Response(500))
        s = Session(
            gstin="29ABCDE1234F1ZW",
            token="tok",
            issued_at=datetime.utcnow() - timedelta(hours=2),
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        )
        assert adapter.session_status(s) is False
