"""WhiteBooksGSPAdapter — GSPClient over HTTP to the WhiteBooks GSP
(https://apisandbox.whitebooks.in), a licensed GSTN Suvidha Provider
operated by BVM IT Consulting Services India Private Limited.

WhiteBooks differs from the generic Master GST-shaped adapter in three
material ways — enough to warrant a separate implementation rather
than parameterising ``adapter_live.py``:

1. **Auth model**. No bearer token, no ``X-Api-Key``. Every request
   carries six custom headers: ``client_id``, ``client_secret``,
   ``gst_username``, ``state_cd``, ``ip_address``, ``txn`` (the session
   token). The first three come from config; ``state_cd`` is the first
   two digits of the GSTIN; ``ip_address`` is our server's public IP.
2. **All endpoints are HTTP GET** except ``/gstr2b/gen2b`` (PUT). Auth
   context that other vendors put in headers goes in the URL query
   string too (``?email=...``).
3. **GSTR-2B is a 3-step async pull**: ``PUT /gstr2b/gen2b`` starts
   generation, ``GET /gstr2b/get2b`` polls status, ``GET /gstr2b/all``
   fetches the payload once ``RTN_31`` is returned. The adapter
   collapses this into a single ``fetch_gstr2b`` call that blocks with
   bounded polling.

Payload encryption (session-key exchange, AES-256 body wrap) is a GSTN
standard that WhiteBooks likely enforces in prod. We ship WITHOUT it:
the sandbox may accept clear JSON, and layering encryption is a
distinct piece of work (RSA keypair on onboarding, AES per session).
If a real call returns ``RET191166`` / ``RET191101``, we know to layer
in an ``adapter_whitebooks_crypto.py`` companion. Until then, the
clear-payload path is what we test.

Stateless. No DB access. Tokens and OTPs are NEVER logged — call sites
use :mod:`app.observability`'s redaction rules.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any, Optional

import httpx

from app.config import settings
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


# ---------------------------------------------------------------------------
# Error code translation — WhiteBooks/GSTN → our GSPError taxonomy
# ---------------------------------------------------------------------------


# The full WhiteBooks/GSTN error catalogue is ~300 codes (see
# docs/gsp-whitebooks-api.md §4). Map only what has a distinct UI
# meaning; the rest fall through to UnknownGSPError with the raw code
# preserved in ``vendor_code`` for the operator to grep in call logs.
_ERROR_CODE_MAP: dict[str, type] = {
    # OTP flow. RET13509 is the single OTP error code — the message
    # text distinguishes "expired" vs "incorrect", but the code is
    # shared. Treat as OTP_INVALID by default; the caller's UI copy
    # already tells the CA to re-request if it says expired.
    "RET13509": OTPInvalid,
    # Session / auth token. RET11407/8/9 all mean "your txn header is
    # stale" — reconnect required.
    "RET11407": SessionExpired,
    "RET11408": SessionExpired,
    "RET11409": SessionExpired,
    "RET11402": SessionExpired,  # Unauthorized — usually IP whitelist / cred expiry
    # 2B async status codes surface via message body during polling
    # rather than as errors. RTN_25 is the only real failure of that flow.
    "RTN_25": GSTNUnavailable,
    # GSTN downstream / retry-with-backoff signals. GSTN has no
    # dedicated rate-limit code; RET13504 (system busy) is the standard
    # throttle-me hint.
    "RET13504": GSTNUnavailable,
    "RET13505": GSTNUnavailable,
    # Payload decryption failures — if we see these, we need to layer in
    # the crypto companion adapter. UNKNOWN keeps the raw code visible
    # in gsp_call_log so the operator sees the pattern.
    "RET191166": UnknownGSPError,
    "RET191101": UnknownGSPError,
    "RET191139": UnknownGSPError,
    # AUTH4037: observed in-wild against apisandbox.whitebooks.in when the
    # WhiteBooks account has valid credentials + enabled sandbox users but
    # does NOT have sandbox API access activated on the subscription side.
    # NOT in the WhiteBooks-supplied error docx. Message text:
    #   "API access is not available or user expiry Duration is less than
    #    or equal to auth token expiry duration"
    # This is an ops-level issue (fixed via WhiteBooks Support enabling
    # the sandbox subscription), not a CA-level one — mapping to
    # UnknownGSPError keeps the code visible in gsp_call_log without
    # sending the CA into a fruitless reconnect loop that a
    # SESSION_EXPIRED classification would trigger.
    "AUTH4037": UnknownGSPError,
}


def _extract_status_and_code(body: Any) -> tuple[str, str, str]:
    """Return (status_cd, error_code, message) from a WhiteBooks JSON body.

    WhiteBooks' clear-payload convention is:
        {"status_cd": "1", ...success fields...}
        {"status_cd": "0", "error": {"error_cd": "RET13509", "message": "..."}}
    We accept a few variants because the Postman collection is inconsistent.
    """
    if not isinstance(body, dict):
        return "", "", ""
    status_cd = str(body.get("status_cd") or "")
    err = body.get("error") or {}
    if not isinstance(err, dict):
        err = {}
    code = str(
        err.get("error_cd")
        or err.get("errorCode")
        or body.get("error_cd")
        or body.get("errorCode")
        or ""
    )
    message = str(
        err.get("message")
        or body.get("message")
        or body.get("status_desc")
        or ""
    )
    return status_cd, code, message


def _translate(resp: httpx.Response) -> dict[str, Any]:
    """Turn a WhiteBooks HTTP response into a parsed dict, or raise.

    Unlike bearer-token vendors, WhiteBooks returns HTTP 200 for
    business errors (``status_cd == "0"``) — so we cannot rely on
    ``resp.raise_for_status()``. We inspect both the HTTP status AND
    the body ``status_cd``.
    """
    try:
        body = resp.json()
    except Exception:
        body = {}

    status_cd, code, message = _extract_status_and_code(body)

    if resp.is_success and status_cd in ("", "1"):
        return body if isinstance(body, dict) else {}

    # Failure path. Build a common kwargs bag for the exception.
    kwargs: dict[str, Any] = {
        "http_status": resp.status_code,
        "vendor_code": code or None,
        "detail": {"body": body},
    }

    # Explicit code map takes precedence.
    exc_cls = _ERROR_CODE_MAP.get(code) if code else None
    if exc_cls is not None:
        raise exc_cls(message or f"WhiteBooks {code}", **kwargs)

    # HTTP-only fallbacks. WhiteBooks does not emit Retry-After, but we
    # honour it if it appears.
    ra = resp.headers.get("Retry-After")
    if ra and ra.isdigit():
        kwargs["retry_after_seconds"] = int(ra)
    if resp.status_code == 429:
        raise RateLimited(message or "rate limited", **kwargs)
    if resp.status_code in (401, 403):
        raise SessionExpired(message or "unauthorized", **kwargs)
    if 500 <= resp.status_code < 600:
        raise GSTNUnavailable(message or "GSTN upstream error", **kwargs)
    raise UnknownGSPError(
        message or f"WhiteBooks error (code={code!r})",
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


# OTP TTL WhiteBooks doesn't publish. GSTN standard is 10 minutes;
# using 5 to match the wider GSP norm and keep the "resend" prompt
# aggressive.
_DEFAULT_OTP_TTL_SECONDS = 300

# Session TTL. GSTN documents 6 hours; WhiteBooks passes through
# unchanged. Response body may or may not carry an explicit "expiry"
# field; fall back to 6h.
_DEFAULT_SESSION_TTL_SECONDS = 6 * 3600

# 2B async polling budget. The GSTN 2B generation for an unusually
# large firm can take a couple of minutes; we cap at 3 min so the API
# request that triggered the pull doesn't hang indefinitely. The
# scheduled sweep path is more forgiving because it runs in RQ.
_POLL_INITIAL_DELAY = 2.0
_POLL_MAX_DELAY = 15.0
_POLL_BUDGET_SECONDS = 180


class WhiteBooksGSPAdapter(GSPClient):
    """HTTP client for the WhiteBooks GSP sandbox / production API.

    Args:
        base_url: e.g. ``https://apisandbox.whitebooks.in``. No trailing slash.
        client_id: from WhiteBooks portal → Credentials.
        client_secret: from WhiteBooks portal → Credentials.
        gst_username: taxpayer's GSTN portal login (sandbox: assigned
            by WhiteBooks, e.g. ``TN_NT2.152383``).
        ip_address: this API server's public IP (GSTN whitelist).
        developer_email: email registered on the WhiteBooks portal.
        timeout: httpx timeout in seconds; default 30.
        transport: httpx transport override; tests use MockTransport.
        clock: injectable ``time.time``-shaped callable for tests.
        sleeper: injectable ``time.sleep``-shaped callable for tests.
    """

    def __init__(
        self,
        base_url: str,
        *,
        client_id: str,
        client_secret: str,
        gst_username: str,
        ip_address: str,
        developer_email: str,
        timeout: float = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
        clock: Optional[Any] = None,
        sleeper: Optional[Any] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client_id = client_id
        self._client_secret = client_secret
        self._gst_username = gst_username
        self._ip_address = ip_address
        self._developer_email = developer_email
        self._timeout = timeout
        self._transport = transport
        self._clock = clock or time.time
        self._sleeper = sleeper or time.sleep

    # ---- httpx wiring -----------------------------------------------------

    def _base_headers(self, txn: str = "") -> dict[str, str]:
        return {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "gst_username": self._gst_username,
            "ip_address": self._ip_address,
            "txn": txn,
            "Accept": "application/json",
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=self._transport,
        )

    @staticmethod
    def _state_cd(gstin: str) -> str:
        """First two chars of GSTIN. Fail fast on malformed inputs."""
        if not gstin or len(gstin) < 2:
            raise UnknownGSPError(
                f"cannot derive state_cd from GSTIN {gstin!r}",
                vendor_code=None,
            )
        return gstin[:2]

    # ---- GSPClient protocol ----------------------------------------------

    def initiate_consent(self, gstin: str) -> ConsentRequest:
        # GET /authentication/otprequest?email=<dev-email>
        headers = {
            **self._base_headers(),
            "state_cd": self._state_cd(gstin),
        }
        with self._client() as c:
            resp = c.get(
                "/authentication/otprequest",
                headers=headers,
                params={"email": self._developer_email},
            )
        body = _translate(resp)
        # Response body: {"status_cd": "1", "status_desc": "OTP sent..."}
        # No txn/request_id is issued at this step — WhiteBooks binds the
        # OTP to the (gst_username, gstin) pair server-side. We generate
        # our own opaque handle so the caller's contract (opaque
        # request_id round-trip) still holds.
        request_id = str(body.get("request_id") or f"wb:{gstin}")
        expires_at = datetime.utcnow() + timedelta(seconds=_DEFAULT_OTP_TTL_SECONDS)
        return ConsentRequest(
            gstin=gstin,
            request_id=request_id,
            expires_at=expires_at,
            vendor_context={},
        )

    def confirm_consent(
        self, consent_request: ConsentRequest, otp: str
    ) -> Session:
        # GET /authentication/authtoken?email=<dev>&otp=<otp>
        headers = {
            **self._base_headers(),
            "state_cd": self._state_cd(consent_request.gstin),
        }
        with self._client() as c:
            resp = c.get(
                "/authentication/authtoken",
                headers=headers,
                params={
                    "email": self._developer_email,
                    "otp": otp,
                },
            )
        body = _translate(resp)
        token = str(body.get("auth_token") or body.get("authtoken") or "")
        if not token:
            raise UnknownGSPError(
                "WhiteBooks authtoken response missing auth_token",
                http_status=resp.status_code,
                detail={"body": body},
            )
        now = datetime.utcnow()
        # WhiteBooks/GSTN don't return a machine-readable expires_at;
        # they return "expiry": "6h" (text). Prefer explicit "expires_at"
        # if a future version adds it; fall back to the default.
        expires_at = now + timedelta(seconds=_DEFAULT_SESSION_TTL_SECONDS)
        vendor_context: dict[str, Any] = {}
        # Stash any encryption material for the future crypto companion.
        for k in ("sek", "session_key", "auth_token_type"):
            if k in body:
                vendor_context[k] = body[k]
        return Session(
            gstin=consent_request.gstin,
            token=token,
            issued_at=now,
            expires_at=expires_at,
            vendor_context=vendor_context,
        )

    def fetch_gstr2b(
        self, session: Session, gstin: str, period: str
    ) -> dict[str, Any]:
        """Blocking 3-step async pull.

        1. PUT /gstr2b/gen2b → request generation.
        2. GET /gstr2b/get2b → poll until status_cd indicates ready
           (RTN_31) or budget exhausted (raise GSTNUnavailable).
        3. GET /gstr2b/all → fetch payload.

        The vendor may skip step 1 and step 2 if 2B is already
        available (typically after the 14th of the month for the
        previous period). We always run gen2b first because it is
        idempotent per the WhiteBooks contract.
        """
        state_cd = self._state_cd(gstin)
        common_headers = {
            **self._base_headers(txn=session.token),
            "state_cd": state_cd,
            "gstin": gstin,
        }

        # Step 1: request generation.
        gen_headers = {
            **common_headers,
            "ret_period": period,
            "Content-Type": "application/json",
        }
        with self._client() as c:
            gen_resp = c.request(
                "PUT",
                "/gstr2b/gen2b",
                headers=gen_headers,
                params={"email": self._developer_email},
                json={},
            )
        gen_body = _translate(gen_resp)
        int_tran_id = str(gen_body.get("int_tran_id") or "")

        # Step 2: poll get2b. If gen2b returned RTN_31 immediately (2B
        # was already generated), we can skip straight to fetch.
        if not self._is_ready(gen_body) and int_tran_id:
            self._poll_until_ready(
                gstin=gstin,
                int_tran_id=int_tran_id,
                headers=common_headers,
            )

        # Step 3: fetch.
        with self._client() as c:
            fetch_resp = c.get(
                "/gstr2b/all",
                headers=common_headers,
                params={
                    "gstin": gstin,
                    "rtnprd": period,
                    "email": self._developer_email,
                },
            )
        return _translate(fetch_resp)

    def _poll_until_ready(
        self,
        *,
        gstin: str,
        int_tran_id: str,
        headers: dict[str, str],
    ) -> None:
        deadline = self._clock() + _POLL_BUDGET_SECONDS
        delay = _POLL_INITIAL_DELAY
        while self._clock() < deadline:
            with self._client() as c:
                resp = c.get(
                    "/gstr2b/get2b",
                    headers=headers,
                    params={
                        "gstin": gstin,
                        "int_tran_id": int_tran_id,
                        "email": self._developer_email,
                    },
                )
            body = _translate(resp)
            if self._is_ready(body):
                return
            self._sleeper(delay)
            delay = min(delay * 1.5, _POLL_MAX_DELAY)
        raise GSTNUnavailable(
            "GSTR-2B generation exceeded polling budget "
            f"({_POLL_BUDGET_SECONDS}s) at WhiteBooks",
            vendor_code="RTN_24",
        )

    @staticmethod
    def _is_ready(body: dict[str, Any]) -> bool:
        """Return True iff the get2b poll body indicates the file is ready.

        WhiteBooks surfaces the async state via the `error_cd` field
        even on 200 responses: RTN_31 = ready, RTN_24 = still generating,
        RTN_32 = another request in progress (also wait), RTN_25 = failed.
        A missing code with status_cd='1' means the flat 2B payload is
        already inline — treat as ready.
        """
        if not isinstance(body, dict):
            return False
        _, code, _ = _extract_status_and_code(body)
        if code == "RTN_31":
            return True
        if code in ("RTN_24", "RTN_32"):
            return False
        if code == "RTN_25":
            raise GSTNUnavailable(
                "WhiteBooks reported GSTR-2B generation failure (RTN_25)",
                vendor_code="RTN_25",
                detail={"body": body},
            )
        # No polling code + status_cd='1' → the file is inline.
        return str(body.get("status_cd") or "") == "1"

    def session_status(self, session: Session) -> bool:
        # WhiteBooks doesn't publish a cheap ping. Fall back to local
        # expiry (as the GSPClient contract permits). A live probe
        # would cost a real API call and defeat the point.
        return not session.is_expired

    def refresh_or_reauth(self, session: Session) -> Optional[Session]:
        # GET /authentication/refreshtoken. Uses the current txn header;
        # a fresh auth_token appears in the response body.
        headers = {
            **self._base_headers(txn=session.token),
            "state_cd": self._state_cd(session.gstin),
        }
        with self._client() as c:
            resp = c.get(
                "/authentication/refreshtoken",
                headers=headers,
                params={"email": self._developer_email},
            )
        try:
            body = _translate(resp)
        except SessionExpired:
            # Session is already dead — no silent refresh possible.
            return None
        token = str(body.get("auth_token") or body.get("authtoken") or "")
        if not token:
            return None
        now = datetime.utcnow()
        return Session(
            gstin=session.gstin,
            token=token,
            issued_at=now,
            expires_at=now + timedelta(seconds=_DEFAULT_SESSION_TTL_SECONDS),
            vendor_context=dict(session.vendor_context),
        )
