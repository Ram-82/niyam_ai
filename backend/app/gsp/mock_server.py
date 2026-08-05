"""Local FastAPI service that mimics a GSP for development + tests.

This is a **first-class citizen** — it runs in docker-compose alongside
the real API and is what every automated e2e and integration test hits
until we hold sandbox credentials for a real vendor. It is NOT a
throwaway stub: fixture files are versioned and the wire shape is
faithful enough that swapping in the real vendor adapter should be the
only change needed.

Endpoints (all under ``/gsp/v1``):

    POST /consent          → issue a fresh consent request (triggers "OTP")
    POST /consent/confirm  → exchange OTP for a session token
    POST /session/status   → check whether a token is still live
    POST /session/refresh  → try to extend a token silently
    POST /gstr2b           → serve the 2B payload for (gstin, period)

Every endpoint honors query params for failure injection so tests can
force error paths without touching internals:

    ?fail=otp_invalid       → OTP endpoints return 400 with vendor_code OTP_MISMATCH
    ?fail=otp_expired       → OTP endpoints return 400 with vendor_code OTP_EXPIRED
    ?fail=session_expired   → data endpoints return 401 with vendor_code SESSION_EXPIRED
    ?fail=gstn_down         → 503 with vendor_code GSTN_UNAVAILABLE
    ?fail=rate_limited      → 429 with Retry-After
    ?fail=consent_revoked   → 403 with vendor_code CONSENT_REVOKED

The mock always accepts the fixed OTP ``123456`` in normal mode. This is
the only test-only backdoor — the real vendor obviously will not have
this, so any adapter code that assumes it is broken code.

Fixtures are keyed by ``(gstin, period)`` and loaded from
``app/gsp/fixtures/gstr2b_<gstin>_<period>.json``. Missing pairs return
a 404 with vendor_code FIXTURE_NOT_FOUND — tests should either add a
fixture or expect UNKNOWN.
"""
from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel


# Test-only constants. Any adapter that inspects these is broken.
FIXED_OTP = "123456"
SESSION_TTL_SECONDS = 30 * 60  # 30 minutes — see TODO-VERIFY-WITH-VENDOR
OTP_TTL_SECONDS = 5 * 60
FIXTURE_DIR = Path(__file__).parent / "fixtures"


app = FastAPI(title="Niyam Mock GSP", version="0.1.0")


# In-memory state. Process lifecycle scope — restart == clean slate.
_consent_requests: dict[str, dict[str, Any]] = {}
_sessions: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Failure injection
# ---------------------------------------------------------------------------


def _maybe_fail(fail: str | None) -> None:
    """Raise the requested failure. Adapter tests set ``fail`` via query."""
    if not fail:
        return
    if fail == "gstn_down":
        raise HTTPException(
            status_code=503,
            detail={"vendor_code": "GSTN_UNAVAILABLE", "message": "GSTN portal is down"},
        )
    if fail == "rate_limited":
        raise HTTPException(
            status_code=429,
            detail={"vendor_code": "RATE_LIMIT", "message": "slow down"},
            headers={"Retry-After": "30"},
        )
    if fail == "otp_invalid":
        raise HTTPException(
            status_code=400,
            detail={"vendor_code": "OTP_MISMATCH", "message": "OTP did not match"},
        )
    if fail == "otp_expired":
        raise HTTPException(
            status_code=400,
            detail={"vendor_code": "OTP_EXPIRED", "message": "OTP window closed"},
        )
    if fail == "session_expired":
        raise HTTPException(
            status_code=401,
            detail={"vendor_code": "SESSION_EXPIRED", "message": "reauth required"},
        )
    if fail == "consent_revoked":
        raise HTTPException(
            status_code=403,
            detail={
                "vendor_code": "CONSENT_REVOKED",
                "message": "taxpayer revoked consent on portal",
            },
        )
    # An unknown 'fail' code is itself an error — surface it so a test typo
    # is loud rather than silent.
    raise HTTPException(
        status_code=418, detail={"vendor_code": "UNKNOWN_FAIL", "message": fail}
    )


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ConsentReq(BaseModel):
    gstin: str


class ConsentResp(BaseModel):
    request_id: str
    expires_at: str
    # Round-tripped by the adapter as opaque vendor_context.
    otp_hint: str = "OTP sent to registered mobile"


class ConfirmReq(BaseModel):
    request_id: str
    otp: str


class ConfirmResp(BaseModel):
    token: str
    issued_at: str
    expires_at: str


class SessionReq(BaseModel):
    token: str


class SessionStatusResp(BaseModel):
    live: bool
    expires_at: str | None = None


class RefreshResp(BaseModel):
    token: str | None
    issued_at: str | None = None
    expires_at: str | None = None


class PullReq(BaseModel):
    token: str
    gstin: str
    period: str  # YYYYMM


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _require_live_session(token: str, gstin: str) -> dict[str, Any]:
    sess = _sessions.get(token)
    if sess is None:
        raise HTTPException(
            status_code=401,
            detail={"vendor_code": "SESSION_UNKNOWN", "message": "token not found"},
        )
    if sess["gstin"] != gstin:
        raise HTTPException(
            status_code=403,
            detail={
                "vendor_code": "GSTIN_MISMATCH",
                "message": "token issued for a different GSTIN",
            },
        )
    if _now() >= sess["expires_at"]:
        raise HTTPException(
            status_code=401,
            detail={"vendor_code": "SESSION_EXPIRED", "message": "reauth required"},
        )
    return sess


# ---------------------------------------------------------------------------
# Fixture lookup
# ---------------------------------------------------------------------------


def _fixture_path(gstin: str, period: str) -> Path:
    return FIXTURE_DIR / f"gstr2b_{gstin}_{period}.json"


def _load_fixture(gstin: str, period: str) -> dict[str, Any]:
    p = _fixture_path(gstin, period)
    if not p.exists():
        raise HTTPException(
            status_code=404,
            detail={
                "vendor_code": "FIXTURE_NOT_FOUND",
                "message": f"no fixture for ({gstin}, {period})",
            },
        )
    with p.open("rb") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "mode": "mock"}


@app.get("/gsp/v1/fixtures")
def list_fixtures() -> dict[str, list[str]]:
    """Debug helper. Not part of any real vendor's API."""
    entries = sorted(p.name for p in FIXTURE_DIR.glob("gstr2b_*.json"))
    return {"fixtures": entries}


@app.post("/gsp/v1/consent", response_model=ConsentResp)
def consent(body: ConsentReq, fail: str | None = Query(default=None)) -> ConsentResp:
    _maybe_fail(fail)
    request_id = secrets.token_urlsafe(16)
    now = _now()
    expires_at = now + timedelta(seconds=OTP_TTL_SECONDS)
    _consent_requests[request_id] = {
        "gstin": body.gstin,
        "created_at": now,
        "expires_at": expires_at,
    }
    return ConsentResp(request_id=request_id, expires_at=_iso(expires_at))


@app.post("/gsp/v1/consent/confirm", response_model=ConfirmResp)
def confirm(body: ConfirmReq, fail: str | None = Query(default=None)) -> ConfirmResp:
    _maybe_fail(fail)
    req = _consent_requests.get(body.request_id)
    if req is None:
        raise HTTPException(
            status_code=400,
            detail={"vendor_code": "CONSENT_UNKNOWN", "message": "no such request"},
        )
    if _now() >= req["expires_at"]:
        _consent_requests.pop(body.request_id, None)
        raise HTTPException(
            status_code=400,
            detail={"vendor_code": "OTP_EXPIRED", "message": "OTP window closed"},
        )
    if body.otp != FIXED_OTP:
        raise HTTPException(
            status_code=400,
            detail={"vendor_code": "OTP_MISMATCH", "message": "OTP did not match"},
        )
    _consent_requests.pop(body.request_id, None)
    now = _now()
    token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(seconds=SESSION_TTL_SECONDS)
    _sessions[token] = {
        "gstin": req["gstin"],
        "issued_at": now,
        "expires_at": expires_at,
    }
    return ConfirmResp(token=token, issued_at=_iso(now), expires_at=_iso(expires_at))


@app.post("/gsp/v1/session/status", response_model=SessionStatusResp)
def session_status(
    body: SessionReq, fail: str | None = Query(default=None)
) -> SessionStatusResp:
    _maybe_fail(fail)
    sess = _sessions.get(body.token)
    if sess is None or _now() >= sess["expires_at"]:
        return SessionStatusResp(live=False)
    return SessionStatusResp(live=True, expires_at=_iso(sess["expires_at"]))


@app.post("/gsp/v1/session/refresh", response_model=RefreshResp)
def session_refresh(
    body: SessionReq, fail: str | None = Query(default=None)
) -> RefreshResp:
    """Silent refresh. Mock policy: refresh succeeds iff the current
    session is still within its window; otherwise the caller must
    re-consent. Real vendors differ — TODO-VERIFY-WITH-VENDOR."""
    _maybe_fail(fail)
    sess = _sessions.get(body.token)
    if sess is None or _now() >= sess["expires_at"]:
        return RefreshResp(token=None)
    now = _now()
    new_expires = now + timedelta(seconds=SESSION_TTL_SECONDS)
    # Issue a fresh token and drop the old (rotation).
    new_token = secrets.token_urlsafe(32)
    _sessions.pop(body.token, None)
    _sessions[new_token] = {
        "gstin": sess["gstin"],
        "issued_at": now,
        "expires_at": new_expires,
    }
    return RefreshResp(
        token=new_token, issued_at=_iso(now), expires_at=_iso(new_expires)
    )


@app.post("/gsp/v1/gstr2b")
def pull_gstr2b(
    body: PullReq, fail: str | None = Query(default=None)
) -> JSONResponse:
    _maybe_fail(fail)
    _require_live_session(body.token, body.gstin)
    payload = _load_fixture(body.gstin, body.period)
    return JSONResponse(payload)
