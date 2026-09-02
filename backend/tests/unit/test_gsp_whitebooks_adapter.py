"""Unit tests for WhiteBooksGSPAdapter.

Hermetic — no network. httpx.MockTransport intercepts every request so
we assert on the exact URL, method, headers, query params, and body.

Load-bearing properties covered:

* Every authenticated request carries the six custom WhiteBooks
  headers: ``client_id``, ``client_secret``, ``gst_username``,
  ``state_cd``, ``ip_address``, ``txn``.
* ``state_cd`` is derived from the first two chars of the GSTIN
  (no extra config value).
* ``?email=`` query param carries the developer email on every call.
* GSTR-2B fetch runs the 3-step async: PUT /gen2b → GET /get2b (poll
  until RTN_31) → GET /all. Polling is bounded and translates
  RTN_25 → GSTNUnavailable.
* WhiteBooks returns HTTP 200 with ``status_cd == "0"`` for business
  errors — the translator must not rely on ``resp.raise_for_status()``.
* Error code map:
    - RET13509 → OTPInvalid
    - RET11407 / RET11408 / RET11409 / RET11402 → SessionExpired
    - RET13504 / RET13505 → GSTNUnavailable
    - RET191166 / RET191101 → UnknownGSPError (signals we need crypto)
* HTTP fallbacks: 429 → RateLimited, 401/403 → SessionExpired,
  5xx → GSTNUnavailable.
* refresh_or_reauth: session-expired response → None (reconnect needed),
  successful refresh → new session with same vendor_context.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx
import pytest

from app.gsp.adapter_whitebooks import WhiteBooksGSPAdapter
from app.gsp.client import (
    ConsentRequest,
    GSTNUnavailable,
    OTPExpired,
    OTPInvalid,
    RateLimited,
    Session,
    SessionExpired,
    UnknownGSPError,
)


BASE_URL = "https://apisandbox.whitebooks.example"
CLIENT_ID = "GSTS_test_client_id"
CLIENT_SECRET = "GSTS_test_client_secret"
GST_USERNAME = "TN_NT2.152383"
IP_ADDRESS = "203.0.113.10"
DEV_EMAIL = "dev@firm.example"
GSTIN_TN = "33AAGCB1286Q1ZB"  # state_cd=33
GSTIN_MH = "27AAGCB1286Q1Z4"  # state_cd=27


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_adapter(
    handler,
    *,
    clock: Optional[Any] = None,
    sleeper: Optional[Any] = None,
) -> WhiteBooksGSPAdapter:
    return WhiteBooksGSPAdapter(
        base_url=BASE_URL,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        gst_username=GST_USERNAME,
        ip_address=IP_ADDRESS,
        developer_email=DEV_EMAIL,
        transport=httpx.MockTransport(handler),
        clock=clock,
        sleeper=sleeper,
    )


def _json_resp(
    status: int,
    body: dict[str, Any],
    headers: Optional[dict] = None,
) -> httpx.Response:
    return httpx.Response(
        status,
        content=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", **(headers or {})},
    )


def _fresh_session(gstin: str = GSTIN_TN) -> Session:
    now = datetime.utcnow()
    return Session(
        gstin=gstin,
        token="live-auth-token-xyz",
        issued_at=now,
        expires_at=now + timedelta(hours=6),
        vendor_context={},
    )


# ---------------------------------------------------------------------------
# Header + URL wiring
# ---------------------------------------------------------------------------


class TestHeaderAndUrlWiring:
    def test_initiate_consent_sends_six_custom_headers(self) -> None:
        captured: dict[str, Any] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["method"] = req.method
            captured["url"] = str(req.url)
            captured["headers"] = dict(req.headers)
            return _json_resp(200, {"status_cd": "1", "status_desc": "OTP sent"})

        adapter = _make_adapter(handler)
        adapter.initiate_consent(GSTIN_TN)

        assert captured["method"] == "GET"
        assert "/authentication/otprequest" in captured["url"]
        assert f"email={DEV_EMAIL}" in captured["url"].replace("%40", "@")
        h = captured["headers"]
        assert h["client_id"] == CLIENT_ID
        assert h["client_secret"] == CLIENT_SECRET
        assert h["gst_username"] == GST_USERNAME
        assert h["state_cd"] == "33"  # first 2 chars of GSTIN_TN
        assert h["ip_address"] == IP_ADDRESS
        # txn is empty on the first call (before authtoken is issued)
        assert h["txn"] == ""

    def test_state_cd_derived_per_gstin(self) -> None:
        """state_cd is NOT config — it's computed from each GSTIN."""
        captured: dict[str, Any] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["state_cd"] = req.headers.get("state_cd")
            return _json_resp(200, {"status_cd": "1"})

        adapter = _make_adapter(handler)
        adapter.initiate_consent(GSTIN_MH)
        assert captured["state_cd"] == "27"

    def test_authtoken_carries_otp_in_query_string(self) -> None:
        captured: dict[str, Any] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            captured["url"] = str(req.url)
            return _json_resp(200, {"status_cd": "1", "auth_token": "T123"})

        adapter = _make_adapter(handler)
        cr = ConsentRequest(
            gstin=GSTIN_TN,
            request_id=f"wb:{GSTIN_TN}",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        adapter.confirm_consent(cr, otp="575757")

        assert "/authentication/authtoken" in captured["url"]
        assert "otp=575757" in captured["url"]
        assert f"email={DEV_EMAIL}" in captured["url"].replace("%40", "@")

    def test_fetch_gstr2b_sends_txn_from_session(self) -> None:
        """Session token becomes the txn header on every 2B call."""
        seen_txns: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            seen_txns.append(req.headers.get("txn") or "")
            if req.method == "PUT":
                return _json_resp(200, {"status_cd": "1", "error_cd": "RTN_31"})
            return _json_resp(
                200,
                {"status_cd": "1", "data": {"docdata": {"b2b": []}}},
            )

        adapter = _make_adapter(handler)
        session = _fresh_session()
        adapter.fetch_gstr2b(session, GSTIN_TN, "072025")

        # gen2b + all → 2 calls, both with the session token as txn.
        assert seen_txns == ["live-auth-token-xyz", "live-auth-token-xyz"]

    def test_gen2b_uses_put_with_empty_json_body(self) -> None:
        captured: dict[str, Any] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "PUT":
                captured["method"] = req.method
                captured["url"] = str(req.url)
                captured["headers"] = dict(req.headers)
                captured["body"] = req.content
                return _json_resp(200, {"status_cd": "1", "error_cd": "RTN_31"})
            return _json_resp(200, {"status_cd": "1", "data": {}})

        adapter = _make_adapter(handler)
        adapter.fetch_gstr2b(_fresh_session(), GSTIN_TN, "072025")

        assert captured["method"] == "PUT"
        assert "/gstr2b/gen2b" in captured["url"]
        assert captured["headers"]["ret_period"] == "072025"
        assert captured["headers"]["gstin"] == GSTIN_TN
        assert captured["headers"].get("content-type") == "application/json"
        assert captured["body"] == b"{}"

    def test_all_endpoint_uses_rtnprd_query(self) -> None:
        """The fetch endpoint uses ?rtnprd=... not ?ret_period=..."""
        captured: dict[str, Any] = {}

        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "PUT":
                return _json_resp(200, {"status_cd": "1", "error_cd": "RTN_31"})
            captured["url"] = str(req.url)
            return _json_resp(200, {"status_cd": "1", "data": {"docdata": {}}})

        adapter = _make_adapter(handler)
        adapter.fetch_gstr2b(_fresh_session(), GSTIN_TN, "072025")

        assert "rtnprd=072025" in captured["url"]
        assert f"gstin={GSTIN_TN}" in captured["url"]


# ---------------------------------------------------------------------------
# Full consent + fetch flow
# ---------------------------------------------------------------------------


class TestFullConsentAndFetchFlow:
    def test_end_to_end_returns_2b_payload(self) -> None:
        expected_data = {
            "chksum": "abc",
            "data": {
                "rtnprd": "072025",
                "gstin": GSTIN_TN,
                "docdata": {
                    "b2b": [{"ctin": "29ZZZZZZZZZZZZZ", "trdnm": "Acme"}],
                },
            },
        }
        call_log: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            if "/authentication/otprequest" in str(req.url):
                call_log.append("otprequest")
                return _json_resp(200, {"status_cd": "1"})
            if "/authentication/authtoken" in str(req.url):
                call_log.append("authtoken")
                return _json_resp(200, {"status_cd": "1", "auth_token": "T-9"})
            if req.method == "PUT" and "/gstr2b/gen2b" in str(req.url):
                call_log.append("gen2b")
                return _json_resp(200, {"status_cd": "1", "error_cd": "RTN_31"})
            if "/gstr2b/all" in str(req.url):
                call_log.append("all")
                return _json_resp(200, {"status_cd": "1", **expected_data})
            raise AssertionError(f"unexpected {req.method} {req.url}")

        adapter = _make_adapter(handler)
        cr = adapter.initiate_consent(GSTIN_TN)
        session = adapter.confirm_consent(cr, otp="575757")
        payload = adapter.fetch_gstr2b(session, GSTIN_TN, "072025")

        assert call_log == ["otprequest", "authtoken", "gen2b", "all"]
        assert payload["chksum"] == "abc"
        assert payload["data"]["gstin"] == GSTIN_TN


# ---------------------------------------------------------------------------
# Async polling
# ---------------------------------------------------------------------------


class TestAsyncPolling:
    def test_poll_until_rtn_31_then_fetch(self) -> None:
        """gen2b returns RTN_24 → get2b polled until RTN_31 → fetch."""
        events: list[str] = []
        get2b_calls = {"n": 0}

        def handler(req: httpx.Request) -> httpx.Response:
            path = req.url.path
            if req.method == "PUT" and path == "/gstr2b/gen2b":
                events.append("gen2b")
                return _json_resp(
                    200,
                    {"status_cd": "1", "int_tran_id": "tran-42", "error_cd": "RTN_24"},
                )
            if path == "/gstr2b/get2b":
                get2b_calls["n"] += 1
                events.append(f"get2b#{get2b_calls['n']}")
                if get2b_calls["n"] < 3:
                    return _json_resp(200, {"status_cd": "1", "error_cd": "RTN_24"})
                return _json_resp(200, {"status_cd": "1", "error_cd": "RTN_31"})
            if path == "/gstr2b/all":
                events.append("all")
                return _json_resp(200, {"status_cd": "1", "data": {"docdata": {}}})
            raise AssertionError(f"unexpected {req.method} {path}")

        sleeps: list[float] = []
        adapter = _make_adapter(handler, sleeper=lambda s: sleeps.append(s))

        payload = adapter.fetch_gstr2b(_fresh_session(), GSTIN_TN, "072025")

        assert events == ["gen2b", "get2b#1", "get2b#2", "get2b#3", "all"]
        # Slept 2 times (between the 3 poll calls).
        assert len(sleeps) == 2
        # Exponential backoff kicks in: second sleep > first.
        assert sleeps[1] > sleeps[0]
        assert payload["data"] == {"docdata": {}}

    def test_rtn_25_during_poll_raises_gstn_unavailable(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "PUT":
                return _json_resp(
                    200,
                    {"status_cd": "1", "int_tran_id": "T1", "error_cd": "RTN_24"},
                )
            # Poll returns RTN_25 = generation failed.
            return _json_resp(200, {"status_cd": "1", "error_cd": "RTN_25"})

        adapter = _make_adapter(handler, sleeper=lambda s: None)
        with pytest.raises(GSTNUnavailable) as exc:
            adapter.fetch_gstr2b(_fresh_session(), GSTIN_TN, "072025")
        assert exc.value.vendor_code == "RTN_25"

    def test_polling_budget_exhaustion_raises_gstn_unavailable(self) -> None:
        """After the polling budget elapses, we bail out rather than hang."""
        # A monotonic clock that jumps 200s per call so the very first
        # while-check on the second iteration is already past deadline.
        clock_state = {"t": 0.0}

        def tick() -> float:
            v = clock_state["t"]
            clock_state["t"] += 200.0
            return v

        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "PUT":
                return _json_resp(
                    200,
                    {"status_cd": "1", "int_tran_id": "T", "error_cd": "RTN_24"},
                )
            # Always still generating.
            return _json_resp(200, {"status_cd": "1", "error_cd": "RTN_24"})

        adapter = _make_adapter(handler, clock=tick, sleeper=lambda s: None)
        with pytest.raises(GSTNUnavailable) as exc:
            adapter.fetch_gstr2b(_fresh_session(), GSTIN_TN, "072025")
        assert exc.value.vendor_code == "RTN_24"

    def test_gen2b_returns_rtn_31_skips_polling(self) -> None:
        """If gen2b returns RTN_31 directly, skip straight to fetch."""
        events: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            if req.method == "PUT":
                events.append("gen2b")
                return _json_resp(200, {"status_cd": "1", "error_cd": "RTN_31"})
            if req.url.path == "/gstr2b/get2b":
                events.append("get2b_UNEXPECTED")
                return _json_resp(200, {"status_cd": "1"})
            events.append("all")
            return _json_resp(200, {"status_cd": "1", "data": {}})

        adapter = _make_adapter(handler, sleeper=lambda s: None)
        adapter.fetch_gstr2b(_fresh_session(), GSTIN_TN, "072025")
        assert events == ["gen2b", "all"]


# ---------------------------------------------------------------------------
# Error translation
# ---------------------------------------------------------------------------


class TestErrorTranslation:
    @pytest.mark.parametrize(
        "vendor_code, expected_exc",
        [
            ("RET13509", OTPInvalid),
            ("RET11407", SessionExpired),
            ("RET11408", SessionExpired),
            ("RET11409", SessionExpired),
            ("RET11402", SessionExpired),
            ("RET13504", GSTNUnavailable),
            ("RET13505", GSTNUnavailable),
            ("RET191166", UnknownGSPError),
            ("RET191101", UnknownGSPError),
        ],
    )
    def test_vendor_code_maps_to_typed_error(
        self, vendor_code: str, expected_exc: type
    ) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return _json_resp(
                200,
                {
                    "status_cd": "0",
                    "error": {"error_cd": vendor_code, "message": "vendor msg"},
                },
            )

        adapter = _make_adapter(handler)
        cr = ConsentRequest(
            gstin=GSTIN_TN,
            request_id="wb:x",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        with pytest.raises(expected_exc) as exc:
            adapter.confirm_consent(cr, otp="000000")
        assert exc.value.vendor_code == vendor_code

    def test_business_error_at_http_200_still_raises(self) -> None:
        """Critical: WhiteBooks returns 200 for business errors — we
        must not silently accept them."""
        def handler(req: httpx.Request) -> httpx.Response:
            return _json_resp(
                200,
                {"status_cd": "0", "error": {"error_cd": "RET13509"}},
            )

        adapter = _make_adapter(handler)
        cr = ConsentRequest(
            gstin=GSTIN_TN,
            request_id="wb:x",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        with pytest.raises(OTPInvalid):
            adapter.confirm_consent(cr, otp="000000")

    def test_429_without_body_maps_to_rate_limited(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(429, content=b"", headers={"Retry-After": "45"})

        adapter = _make_adapter(handler)
        with pytest.raises(RateLimited) as exc:
            adapter.initiate_consent(GSTIN_TN)
        assert exc.value.retry_after_seconds == 45

    def test_401_without_body_maps_to_session_expired(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(401, content=b"")

        adapter = _make_adapter(handler)
        with pytest.raises(SessionExpired):
            adapter.fetch_gstr2b(_fresh_session(), GSTIN_TN, "072025")

    def test_5xx_without_body_maps_to_gstn_unavailable(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return httpx.Response(503, content=b"")

        adapter = _make_adapter(handler)
        with pytest.raises(GSTNUnavailable):
            adapter.initiate_consent(GSTIN_TN)

    def test_unknown_code_maps_to_unknown_with_code_preserved(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return _json_resp(
                200,
                {
                    "status_cd": "0",
                    "error": {"error_cd": "NEVER_SEEN_BEFORE", "message": "?"},
                },
            )

        adapter = _make_adapter(handler)
        with pytest.raises(UnknownGSPError) as exc:
            adapter.initiate_consent(GSTIN_TN)
        assert exc.value.vendor_code == "NEVER_SEEN_BEFORE"


# ---------------------------------------------------------------------------
# Response-shape defensiveness
# ---------------------------------------------------------------------------


class TestResponseShapeDefensiveness:
    def test_confirm_without_auth_token_raises_unknown(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            # 200, status_cd=1, but no auth_token in body.
            return _json_resp(200, {"status_cd": "1"})

        adapter = _make_adapter(handler)
        cr = ConsentRequest(
            gstin=GSTIN_TN,
            request_id="wb:x",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        with pytest.raises(UnknownGSPError):
            adapter.confirm_consent(cr, otp="575757")

    def test_malformed_gstin_raises_unknown_at_state_cd(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            raise AssertionError("should not hit the wire")

        adapter = _make_adapter(handler)
        with pytest.raises(UnknownGSPError):
            adapter.initiate_consent("")

    def test_confirm_captures_sek_into_vendor_context(self) -> None:
        """When the response carries an sek (session encryption key),
        stash it in vendor_context so the future crypto companion can
        read it back."""
        def handler(req: httpx.Request) -> httpx.Response:
            return _json_resp(
                200,
                {
                    "status_cd": "1",
                    "auth_token": "T-1",
                    "sek": "base64-enc-aes-key",
                },
            )

        adapter = _make_adapter(handler)
        cr = ConsentRequest(
            gstin=GSTIN_TN,
            request_id="wb:x",
            expires_at=datetime.utcnow() + timedelta(minutes=5),
        )
        session = adapter.confirm_consent(cr, otp="575757")
        assert session.vendor_context.get("sek") == "base64-enc-aes-key"


# ---------------------------------------------------------------------------
# refresh_or_reauth
# ---------------------------------------------------------------------------


class TestRefreshOrReauth:
    def test_refresh_success_returns_new_session(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            assert "/authentication/refreshtoken" in str(req.url)
            return _json_resp(200, {"status_cd": "1", "auth_token": "T-NEW"})

        adapter = _make_adapter(handler)
        old = _fresh_session()
        new = adapter.refresh_or_reauth(old)
        assert new is not None
        assert new.token == "T-NEW"
        assert new.gstin == old.gstin

    def test_refresh_session_expired_returns_none(self) -> None:
        """Session-expired response is the 'reconnect needed' signal — we
        translate that to None, not an exception."""
        def handler(req: httpx.Request) -> httpx.Response:
            return _json_resp(
                200,
                {"status_cd": "0", "error": {"error_cd": "RET11407"}},
            )

        adapter = _make_adapter(handler)
        assert adapter.refresh_or_reauth(_fresh_session()) is None

    def test_refresh_missing_token_returns_none(self) -> None:
        def handler(req: httpx.Request) -> httpx.Response:
            return _json_resp(200, {"status_cd": "1"})

        adapter = _make_adapter(handler)
        assert adapter.refresh_or_reauth(_fresh_session()) is None


# ---------------------------------------------------------------------------
# session_status
# ---------------------------------------------------------------------------


class TestSessionStatus:
    def test_true_for_unexpired(self) -> None:
        adapter = _make_adapter(lambda req: _json_resp(200, {}))
        assert adapter.session_status(_fresh_session()) is True

    def test_false_for_expired(self) -> None:
        adapter = _make_adapter(lambda req: _json_resp(200, {}))
        past = datetime.utcnow() - timedelta(hours=1)
        session = Session(
            gstin=GSTIN_TN,
            token="stale",
            issued_at=past - timedelta(hours=6),
            expires_at=past,
        )
        assert adapter.session_status(session) is False
