"""LiveGSPAdapter — GSPClient over HTTP to a real licensed GSP vendor.

Ship-time shape targets Master GST's public sandbox
(``https://sandbox.mastergst.com``) because it has the most accessible
free developer tier and per-call production pricing that fits a
single-firm pilot. Other vendors (Cygnet, TaxGenie, ClearTax, Vayana)
speak superficially similar REST but differ in:

* auth header name (Master GST: ``X-Api-Key``; others: ``Authorization: Bearer``,
  or client_id + client_secret exchanged for an OAuth token first).
* URL layout (Master GST uses ``/api/v0.4/gstr2b/{gstin}/{period}``;
  others use POST bodies for gstin+period).
* OTP flow shape (some issue a request_id in the initiate response and
  expect it back on verify; some use a session-request-id header).
* session semantics (some issue a long-lived token; some require
  reauth per call).

The pattern for a second vendor is: fork this file into
``adapter_cygnet.py`` etc., override the four private ``_*_url`` helpers
and the four vendor-response ``_translate_*`` functions, and register
another ``gsp_mode`` string in :func:`app.gsp.service.get_adapter`.

The vendor's error codes are translated into our
:mod:`app.gsp.client` taxonomy the same way :mod:`app.gsp.adapter_mock`
does — the map here is a superset covering both Master GST and the
common HTTP status shapes.

Stateless. No DB access. No logging of tokens or OTPs — the log lines
that mention these values MUST redact them (see
:mod:`app.observability`'s redaction rules).
"""
from __future__ import annotations

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
# Response translation — vendor → our GSPError taxonomy
# ---------------------------------------------------------------------------


def _parse_dt(s: Optional[str], *, default: Optional[datetime] = None) -> datetime:
    """Best-effort ISO-8601 parse. Master GST omits tzinfo — we treat as UTC
    naive so :attr:`Session.is_expired` (which uses ``datetime.utcnow()``)
    compares consistently."""
    if s is None:
        if default is not None:
            return default
        raise ValueError("missing datetime string")
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is not None:
        dt = dt.astimezone(tz=None).replace(tzinfo=None)
    return dt


# Vendor error codes → our exception classes. Master GST uses shorter
# codes; the fallbacks cover the plainer status_code-only failures too.
_ERROR_CODE_MAP: dict[str, type] = {
    # OTP flow
    "OTP_MISMATCH": OTPInvalid,
    "OTP_INVALID": OTPInvalid,
    "OTP_WRONG": OTPInvalid,
    "OTP_EXPIRED": OTPExpired,
    "OTP_TIMEOUT": OTPExpired,
    # Session / auth
    "SESSION_EXPIRED": SessionExpired,
    "SESSION_UNKNOWN": SessionExpired,
    "AUTH_TOKEN_EXPIRED": SessionExpired,
    "TOKEN_EXPIRED": SessionExpired,
    "AUTH_TOKEN_INVALID": SessionExpired,
    # Consent
    "CONSENT_REVOKED": ConsentRevoked,
    "CONSENT_NOT_GIVEN": ConsentRevoked,
    # Rate + backpressure
    "RATE_LIMIT": RateLimited,
    "RATE_LIMITED": RateLimited,
    "THROTTLED": RateLimited,
    # Upstream GSTN
    "GSTN_UNAVAILABLE": GSTNUnavailable,
    "GSTN_DOWN": GSTNUnavailable,
    "GSTN_ERROR": GSTNUnavailable,
}


def _translate(resp: httpx.Response) -> None:
    """Map vendor HTTP failure → our taxonomy. No-op on 2xx."""
    if resp.is_success:
        return
    try:
        body = resp.json()
    except Exception:
        body = {}
    # Vendors nest the code differently. Support the two common shapes:
    #   {"error_cd": "OTP_EXPIRED", "message": "..."}
    #   {"detail": {"vendor_code": "OTP_EXPIRED", "message": "..."}}
    code = ""
    message = ""
    detail: dict[str, Any] = {}
    if isinstance(body, dict):
        code = str(
            body.get("error_cd")
            or body.get("errorCode")
            or body.get("code")
            or (body.get("detail") or {}).get("vendor_code")
            or ""
        )
        message = str(
            body.get("message")
            or (body.get("detail") or {}).get("message")
            or resp.reason_phrase
            or "GSP error"
        )
        detail = {"body": body}
    else:
        message = resp.reason_phrase or "GSP error"

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

    exc_cls = _ERROR_CODE_MAP.get(code)
    if exc_cls is not None:
        raise exc_cls(message, **kwargs)

    # HTTP-only fallbacks — a vendor that returned a 429 without a body
    # code is still rate-limiting us; a 5xx without a body code is still
    # a GSTN-side issue we should back off from.
    if resp.status_code == 429:
        raise RateLimited(message, **kwargs)
    if resp.status_code in (401, 403):
        # Distinguish "session bad" (retry with reauth) from "consent
        # revoked" (surface to CA) when the vendor gave us no code —
        # default to session-expired so the caller re-authenticates
        # before assuming the MSME pulled consent.
        raise SessionExpired(message, **kwargs)
    if 500 <= resp.status_code < 600:
        raise GSTNUnavailable(message, **kwargs)
    raise UnknownGSPError(message, **kwargs)


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


# The vendor may cap OTP validity somewhere between 90s and 300s. When
# the initiate response omits an explicit expires_at, we default to this
# so downstream code has a concrete timestamp to compare against.
_DEFAULT_OTP_TTL_SECONDS = 300

# Session TTL default when the vendor omits expires_at from the confirm
# response. Master GST issues 6-hour sessions historically; keep this
# conservative so we surface reauth-needed rather than hit "session
# expired" mid-pull.
_DEFAULT_SESSION_TTL_SECONDS = 3600


class LiveGSPAdapter(GSPClient):
    """HTTP client for a real GSP vendor.

    Args:
        base_url: e.g. ``https://sandbox.mastergst.com``. No trailing slash.
        api_key: value for the ``X-Api-Key`` header on every call.
        path_prefix: path segment inserted before every endpoint, e.g.
            ``/api/v0.4``. Defaults to :attr:`Settings.gsp_live_path_prefix`.
        timeout: httpx client timeout in seconds; default 30 (the vendor
            round-trips through GSTN, which can be slow).
        client_id / client_secret: reserved for vendors that require an
            OAuth token exchange before ``X-Api-Key`` auth. Unused by the
            Master GST profile.
        transport: httpx transport override; only used by tests via
            ``httpx.MockTransport``.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        path_prefix: Optional[str] = None,
        timeout: float = 30.0,
        client_id: str = "",
        client_secret: str = "",
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._path_prefix = (path_prefix or settings.gsp_live_path_prefix).rstrip("/")
        self._timeout = timeout
        self._client_id = client_id
        self._client_secret = client_secret
        self._transport = transport

    # ---- httpx wiring -----------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "X-Api-Key": self._api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=self._base_url,
            timeout=self._timeout,
            transport=self._transport,
        )

    def _url(self, *parts: str) -> str:
        """Join ``path_prefix`` + parts into an absolute path."""
        tail = "/".join(p.strip("/") for p in parts if p)
        return f"{self._path_prefix}/{tail}" if tail else self._path_prefix

    # ---- GSPClient protocol ----------------------------------------------

    def initiate_consent(self, gstin: str) -> ConsentRequest:
        # Master GST: POST /api/<v>/gstr2b/otp/{gstin}
        with self._client() as c:
            resp = c.post(
                self._url("gstr2b", "otp", gstin),
                headers=self._headers(),
            )
        _translate(resp)
        body = resp.json()
        # Master GST returns {"request_id": "...", "expires_at": "..."}.
        # Some fixture responses just return {"txn": "...", "status": ...}
        # — accept either.
        request_id = str(body.get("request_id") or body.get("txn") or "")
        if not request_id:
            raise UnknownGSPError(
                "vendor initiate_consent response missing request_id / txn",
                http_status=resp.status_code,
                detail={"body": body},
            )
        expires_at = _parse_dt(
            body.get("expires_at"),
            default=datetime.utcnow() + timedelta(seconds=_DEFAULT_OTP_TTL_SECONDS),
        )
        vendor_context: dict[str, Any] = {}
        # Round-trip anything else the vendor may want back on verify.
        for k in ("txn", "session_request_id", "requestId"):
            if k in body:
                vendor_context[k] = body[k]
        return ConsentRequest(
            gstin=gstin,
            request_id=request_id,
            expires_at=expires_at,
            vendor_context=vendor_context,
        )

    def confirm_consent(
        self, consent_request: ConsentRequest, otp: str
    ) -> Session:
        # Master GST: POST /api/<v>/gstr2b/otp/{gstin}/verify with body
        # {"otp": "...", "request_id": "..."}.
        payload: dict[str, Any] = {
            "otp": otp,
            "request_id": consent_request.request_id,
        }
        # Include any vendor-round-tripped context in the payload — some
        # vendors expect the transaction id back verbatim.
        payload.update(consent_request.vendor_context)

        with self._client() as c:
            resp = c.post(
                self._url("gstr2b", "otp", consent_request.gstin, "verify"),
                headers=self._headers(),
                json=payload,
            )
        _translate(resp)
        body = resp.json()
        token = str(body.get("token") or body.get("auth_token") or "")
        if not token:
            raise UnknownGSPError(
                "vendor confirm_consent response missing token",
                http_status=resp.status_code,
                detail={"body": body},
            )
        now = datetime.utcnow()
        issued_at = _parse_dt(body.get("issued_at"), default=now)
        expires_at = _parse_dt(
            body.get("expires_at"),
            default=now + timedelta(seconds=_DEFAULT_SESSION_TTL_SECONDS),
        )
        vendor_context: dict[str, Any] = dict(consent_request.vendor_context)
        for k in ("refresh_token", "session_id", "auth_token_type"):
            if k in body:
                vendor_context[k] = body[k]
        return Session(
            gstin=consent_request.gstin,
            token=token,
            issued_at=issued_at,
            expires_at=expires_at,
            vendor_context=vendor_context,
        )

    def fetch_gstr2b(
        self, session: Session, gstin: str, period: str
    ) -> dict[str, Any]:
        # Master GST: GET /api/<v>/gstr2b/{gstin}/{period} with the
        # session token in a header (some deployments accept X-Auth-Token
        # or Authorization: Bearer — try Authorization first, fall back
        # to X-Auth-Token if the vendor rejects it).
        headers = {
            **self._headers(),
            "Authorization": f"Bearer {session.token}",
            "X-Auth-Token": session.token,
        }
        with self._client() as c:
            resp = c.get(
                self._url("gstr2b", gstin, period),
                headers=headers,
            )
        _translate(resp)
        return resp.json()

    def session_status(self, session: Session) -> bool:
        # Vendors don't uniformly expose a cheap probe. Master GST has
        # no dedicated /session/status — the accepted pattern is a HEAD
        # against a cheap endpoint. To avoid burning a full 2B pull just
        # to check aliveness, fall back to :attr:`Session.is_expired`
        # (as :meth:`GSPClient.session_status`'s docstring permits).
        return not session.is_expired

    def refresh_or_reauth(self, session: Session) -> Optional[Session]:
        # If the vendor's confirm_consent response carried a refresh_token
        # we can trade it for a fresh session; else the caller must run
        # the OTP flow again.
        refresh = session.vendor_context.get("refresh_token")
        if not refresh:
            return None

        with self._client() as c:
            resp = c.post(
                self._url("session", "refresh"),
                headers=self._headers(),
                json={"refresh_token": refresh},
            )
        _translate(resp)
        body = resp.json()
        token = str(body.get("token") or body.get("auth_token") or "")
        if not token:
            return None
        now = datetime.utcnow()
        return Session(
            gstin=session.gstin,
            token=token,
            issued_at=_parse_dt(body.get("issued_at"), default=now),
            expires_at=_parse_dt(
                body.get("expires_at"),
                default=now + timedelta(seconds=_DEFAULT_SESSION_TTL_SECONDS),
            ),
            vendor_context=dict(session.vendor_context),
        )
