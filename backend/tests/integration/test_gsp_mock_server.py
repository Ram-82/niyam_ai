"""Integration tests for the MockGSPServer.

Runs against the FastAPI app in-process via TestClient — no docker
needed. The docker-compose ``gsp-mock`` service uses the same app; if
these tests pass, the container will behave the same way.

Every failure-injection query param that the real error taxonomy cares
about is exercised here. This is the ground truth for the adapter
tests (Stage 2), which will translate these HTTP responses into
GSPError subclasses.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.gsp.mock_server import FIXED_OTP, app as mock_app


# The mock server keeps process-local state (consent requests + sessions).
# We reset it between tests by re-importing / clearing dicts.
def _fresh_client() -> TestClient:
    from app.gsp import mock_server as m

    m._consent_requests.clear()
    m._sessions.clear()
    return TestClient(mock_app)


CLIENT_GSTIN = "29ZZZZZ9999Z9Z9"


def _consent_and_confirm(c: TestClient, gstin: str = CLIENT_GSTIN) -> str:
    r = c.post("/gsp/v1/consent", json={"gstin": gstin})
    assert r.status_code == 200, r.text
    rid = r.json()["request_id"]
    r = c.post(
        "/gsp/v1/consent/confirm", json={"request_id": rid, "otp": FIXED_OTP}
    )
    assert r.status_code == 200, r.text
    return r.json()["token"]


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_health_ok() -> None:
    c = _fresh_client()
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "mode": "mock"}


def test_fixture_listing_includes_both_periods_and_two_gstins() -> None:
    c = _fresh_client()
    r = c.get("/gsp/v1/fixtures")
    assert r.status_code == 200
    names = r.json()["fixtures"]
    # (gstin, period) key: two periods for the primary client + one
    # alternate-taxpayer fixture for adapter tests.
    assert "gstr2b_29ZZZZZ9999Z9Z9_202606.json" in names
    assert "gstr2b_29ZZZZZ9999Z9Z9_202605.json" in names
    assert "gstr2b_27BBBBB1111B2Z6_202606.json" in names


def test_full_happy_path_consent_confirm_pull() -> None:
    c = _fresh_client()
    token = _consent_and_confirm(c)
    r = c.post(
        "/gsp/v1/gstr2b",
        json={"token": token, "gstin": CLIENT_GSTIN, "period": "202606"},
    )
    assert r.status_code == 200, r.text
    payload = r.json()
    # Same shape parse_gstr2b_json expects: data.docdata.b2b[]
    assert payload["data"]["rtnprd"] == "062026"
    assert payload["data"]["docdata"]["b2b"][0]["ctin"] == "29AAAAA0000A1Z5"


def test_prior_period_served() -> None:
    c = _fresh_client()
    token = _consent_and_confirm(c)
    r = c.post(
        "/gsp/v1/gstr2b",
        json={"token": token, "gstin": CLIENT_GSTIN, "period": "202605"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["rtnprd"] == "052026"


def test_second_taxpayer_served() -> None:
    other = "27BBBBB1111B2Z6"
    c = _fresh_client()
    token = _consent_and_confirm(c, gstin=other)
    r = c.post(
        "/gsp/v1/gstr2b",
        json={"token": token, "gstin": other, "period": "202606"},
    )
    assert r.status_code == 200
    assert r.json()["data"]["gstin"] == other


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


def test_session_status_true_after_confirm_false_for_unknown_token() -> None:
    c = _fresh_client()
    token = _consent_and_confirm(c)
    r = c.post("/gsp/v1/session/status", json={"token": token})
    assert r.status_code == 200
    assert r.json()["live"] is True

    r = c.post("/gsp/v1/session/status", json={"token": "nonsense"})
    assert r.status_code == 200
    assert r.json()["live"] is False


def test_session_refresh_rotates_token_and_extends_expiry() -> None:
    c = _fresh_client()
    token = _consent_and_confirm(c)
    r = c.post("/gsp/v1/session/refresh", json={"token": token})
    assert r.status_code == 200
    body = r.json()
    assert body["token"] is not None
    assert body["token"] != token  # rotation
    # Old token is dead
    r = c.post("/gsp/v1/session/status", json={"token": token})
    assert r.json()["live"] is False
    # New token is alive
    r = c.post("/gsp/v1/session/status", json={"token": body["token"]})
    assert r.json()["live"] is True


def test_refresh_returns_null_when_token_unknown() -> None:
    c = _fresh_client()
    r = c.post("/gsp/v1/session/refresh", json={"token": "nope"})
    assert r.status_code == 200
    assert r.json()["token"] is None


def test_gstin_mismatch_between_token_and_pull_is_rejected() -> None:
    c = _fresh_client()
    token = _consent_and_confirm(c, gstin=CLIENT_GSTIN)
    r = c.post(
        "/gsp/v1/gstr2b",
        json={"token": token, "gstin": "27BBBBB1111B2Z6", "period": "202606"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["vendor_code"] == "GSTIN_MISMATCH"


def test_unknown_session_token_on_pull() -> None:
    c = _fresh_client()
    r = c.post(
        "/gsp/v1/gstr2b",
        json={"token": "not-a-real-token", "gstin": CLIENT_GSTIN, "period": "202606"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["vendor_code"] == "SESSION_UNKNOWN"


# ---------------------------------------------------------------------------
# OTP paths
# ---------------------------------------------------------------------------


def test_wrong_otp_rejected() -> None:
    c = _fresh_client()
    r = c.post("/gsp/v1/consent", json={"gstin": CLIENT_GSTIN})
    rid = r.json()["request_id"]
    r = c.post(
        "/gsp/v1/consent/confirm", json={"request_id": rid, "otp": "000000"}
    )
    assert r.status_code == 400
    assert r.json()["detail"]["vendor_code"] == "OTP_MISMATCH"


def test_consent_unknown_request_id() -> None:
    c = _fresh_client()
    r = c.post(
        "/gsp/v1/consent/confirm",
        json={"request_id": "nonexistent", "otp": FIXED_OTP},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["vendor_code"] == "CONSENT_UNKNOWN"


# ---------------------------------------------------------------------------
# Missing fixture
# ---------------------------------------------------------------------------


def test_missing_fixture_yields_404() -> None:
    c = _fresh_client()
    token = _consent_and_confirm(c)
    r = c.post(
        "/gsp/v1/gstr2b",
        json={"token": token, "gstin": CLIENT_GSTIN, "period": "199901"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["vendor_code"] == "FIXTURE_NOT_FOUND"


# ---------------------------------------------------------------------------
# Failure injection — one test per taxonomy entry
# ---------------------------------------------------------------------------


def test_fail_gstn_down_on_consent() -> None:
    c = _fresh_client()
    r = c.post("/gsp/v1/consent?fail=gstn_down", json={"gstin": CLIENT_GSTIN})
    assert r.status_code == 503
    assert r.json()["detail"]["vendor_code"] == "GSTN_UNAVAILABLE"


def test_fail_rate_limited_returns_retry_after() -> None:
    c = _fresh_client()
    r = c.post("/gsp/v1/consent?fail=rate_limited", json={"gstin": CLIENT_GSTIN})
    assert r.status_code == 429
    assert r.headers.get("Retry-After") == "30"
    assert r.json()["detail"]["vendor_code"] == "RATE_LIMIT"


def test_fail_otp_invalid_on_confirm() -> None:
    c = _fresh_client()
    r = c.post("/gsp/v1/consent", json={"gstin": CLIENT_GSTIN})
    rid = r.json()["request_id"]
    r = c.post(
        "/gsp/v1/consent/confirm?fail=otp_invalid",
        json={"request_id": rid, "otp": FIXED_OTP},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["vendor_code"] == "OTP_MISMATCH"


def test_fail_otp_expired_on_confirm() -> None:
    c = _fresh_client()
    r = c.post("/gsp/v1/consent", json={"gstin": CLIENT_GSTIN})
    rid = r.json()["request_id"]
    r = c.post(
        "/gsp/v1/consent/confirm?fail=otp_expired",
        json={"request_id": rid, "otp": FIXED_OTP},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["vendor_code"] == "OTP_EXPIRED"


def test_fail_session_expired_on_pull() -> None:
    c = _fresh_client()
    token = _consent_and_confirm(c)
    r = c.post(
        "/gsp/v1/gstr2b?fail=session_expired",
        json={"token": token, "gstin": CLIENT_GSTIN, "period": "202606"},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["vendor_code"] == "SESSION_EXPIRED"


def test_fail_consent_revoked_on_pull() -> None:
    c = _fresh_client()
    token = _consent_and_confirm(c)
    r = c.post(
        "/gsp/v1/gstr2b?fail=consent_revoked",
        json={"token": token, "gstin": CLIENT_GSTIN, "period": "202606"},
    )
    assert r.status_code == 403
    assert r.json()["detail"]["vendor_code"] == "CONSENT_REVOKED"
