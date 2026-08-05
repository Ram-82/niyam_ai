"""Vendor-agnostic GSP client protocol.

The concrete adapters (``MockGSPAdapter`` today; ``CygnetAdapter`` /
``IRISAdapter`` / ``MastersIndiaAdapter`` / ``ClearTaxAdapter`` when a real
vendor lands) must implement :class:`GSPClient`. That is the ONLY place
vendor code lives; everything above this line (consent API, session
storage, scheduler, ingestion reuse, error taxonomy, cost metering) is
vendor-neutral.

Wire flow modeled here — matches the standard GSTN "ASP → GSP → GSTN"
handshake, but ANY GSTN- or vendor-specific detail below is flagged
"TODO-VERIFY-WITH-VENDOR" because we do not yet hold sandbox
credentials:

    1. initiate_consent(gstin)
         Backend asks the GSP to trigger an OTP against the mobile number
         registered on the GSTIN. Returns a ``ConsentRequest`` handle
         (transaction id + vendor-supplied context we must round-trip).
         TODO-VERIFY-WITH-VENDOR: the exact request/response envelope
         varies per vendor. Cygnet uses ``requestid``; IRIS uses
         ``txn``; ClearTax uses ``sessionRequestId``. The adapter is the
         translation layer.

    2. confirm_consent(consent_request, otp)
         Backend forwards the OTP the MSME owner reads out to the CA
         (see UI copy: OTP goes to GSTIN-registered mobile, not the CA's
         phone). Returns a :class:`Session` that carries the vendor's
         session token + our own expiry-tracking metadata.
         TODO-VERIFY-WITH-VENDOR: session TTLs differ. GSTN documents
         6 hours for authenticated sessions but the effective TTL at
         the GSP layer is often shorter and refresh semantics differ.

    3. fetch_gstr2b(session, gstin, period)
         Pulls the raw 2B payload for a period. Returns whatever JSON
         the vendor returns — we DO NOT reshape it here. The existing
         :func:`app.ingestion.gstr2b_parser.parse_gstr2b_json` accepts
         both known top-level shapes and the vendor should pass through
         the GSTN payload as-is (mock server does; real vendors
         usually do; ClearTax is known to wrap it — TODO-VERIFY-WITH-VENDOR).

    4. session_status(session)
         Cheap health check. Used by the "reconnect needed" surfacing so
         we never silently fail a scheduled pull.

    5. refresh_or_reauth(session)
         If the vendor supports a silent refresh (extends the session
         without another OTP), do it. Otherwise raise
         :class:`ConsentRevoked` / :class:`SessionExpired` so the CA
         is prompted to reconnect.

Everything else — retries, cost metering, encryption at rest,
consent_log writes, gstn_pull rows, ingestion reuse — lives in the
caller. Adapters must be thin, stateless, and MUST NOT touch the DB.

Error taxonomy (see :class:`GSPErrorKind`) is what the caller maps to
UI states. Every adapter MUST raise exceptions from this module — never
a vendor-specific one — so the caller can code once.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


class GSPErrorKind(str, enum.Enum):
    """Stable error taxonomy. Adapters translate vendor codes into these.

    UI copy and retry policy branch on the ``kind``:

        OTP_INVALID       — user-facing: "OTP didn't match — try again."
                            Retry policy: never auto-retry.
        OTP_EXPIRED       — user-facing: "OTP expired — request a new one."
                            Retry policy: never auto-retry.
        SESSION_EXPIRED   — user-facing: "Session expired — reconnect this GSTIN."
                            Retry policy: never auto-retry (triggers reconnect UI).
        GSTN_UNAVAILABLE  — user-facing: "GSTN portal is down. Retrying."
                            Retry policy: exponential backoff, max 3.
        RATE_LIMITED      — user-facing: "Slow down — queued."
                            Retry policy: backoff + honor Retry-After.
        CONSENT_REVOKED   — user-facing: "Consent revoked — reconnect."
                            Retry policy: never auto-retry.
        UNKNOWN           — user-facing: generic; full context logged.
                            Retry policy: never auto-retry.
    """

    OTP_INVALID = "otp_invalid"
    OTP_EXPIRED = "otp_expired"
    SESSION_EXPIRED = "session_expired"
    GSTN_UNAVAILABLE = "gstn_unavailable"
    RATE_LIMITED = "rate_limited"
    CONSENT_REVOKED = "consent_revoked"
    UNKNOWN = "unknown"


class GSPError(Exception):
    """Base for every error an adapter may raise.

    Attributes:
        kind: taxonomy entry (see :class:`GSPErrorKind`).
        http_status: HTTP status from the GSP call, if any, for the
            ``gsp_call_log`` row.
        retry_after_seconds: honored by the caller for RATE_LIMITED.
        vendor_code: raw code string as returned by the vendor. Logged
            but NEVER shown to the user.
        detail: free-form vendor payload. Logged, never shown.
    """

    kind: GSPErrorKind = GSPErrorKind.UNKNOWN

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        retry_after_seconds: int | None = None,
        vendor_code: str | None = None,
        detail: Any = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.retry_after_seconds = retry_after_seconds
        self.vendor_code = vendor_code
        self.detail = detail


class OTPInvalid(GSPError):
    kind = GSPErrorKind.OTP_INVALID


class OTPExpired(GSPError):
    kind = GSPErrorKind.OTP_EXPIRED


class SessionExpired(GSPError):
    kind = GSPErrorKind.SESSION_EXPIRED


class GSTNUnavailable(GSPError):
    kind = GSPErrorKind.GSTN_UNAVAILABLE


class RateLimited(GSPError):
    kind = GSPErrorKind.RATE_LIMITED


class ConsentRevoked(GSPError):
    kind = GSPErrorKind.CONSENT_REVOKED


class UnknownGSPError(GSPError):
    kind = GSPErrorKind.UNKNOWN


@dataclass(frozen=True)
class ConsentRequest:
    """Handle returned from :meth:`GSPClient.initiate_consent`.

    Round-tripped verbatim to :meth:`GSPClient.confirm_consent`. The
    ``vendor_context`` bag lets a vendor stash anything it needs to
    correlate the OTP submission (transaction id, request id, session
    request id — whatever it calls it). Callers must treat it as opaque.
    """

    gstin: str
    request_id: str
    expires_at: datetime
    vendor_context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Session:
    """A live GSP session.

    ``token`` is the bearer credential the vendor accepts on subsequent
    calls. The caller encrypts ``token`` at rest (see
    :mod:`app.gsp.crypto`) — this dataclass carries the plaintext only
    inside a request.

    ``vendor_context`` is round-tripped on every subsequent adapter
    call. It may carry vendor-specific state (auth token type,
    refresh token, session request id) — opaque to callers.

    TODO-VERIFY-WITH-VENDOR: session refresh semantics. Some vendors
    issue a refresh token, some require a full OTP redo. The
    :meth:`GSPClient.refresh_or_reauth` seam handles both.
    """

    gstin: str
    token: str
    issued_at: datetime
    expires_at: datetime
    vendor_context: dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() >= self.expires_at


@runtime_checkable
class GSPClient(Protocol):
    """The seam every vendor implements.

    Adapters MUST be stateless and MUST NOT touch the database. They may
    hold configuration (base URL, api key) passed at construction time.
    All persistence — sessions, call logs, consent_log rows, gstn_pull
    rows — is the caller's job.

    Every method raises subclasses of :class:`GSPError` on failure; the
    caller (never the adapter) decides on retry, UI mapping, and logging.
    """

    def initiate_consent(self, gstin: str) -> ConsentRequest:
        """Ask the vendor to trigger an OTP to the GSTIN-registered mobile.

        Raises:
            GSTNUnavailable: GSTN portal is down at the vendor.
            RateLimited: vendor is throttling this firm.
            UnknownGSPError: anything else.
        """
        ...

    def confirm_consent(
        self, consent_request: ConsentRequest, otp: str
    ) -> Session:
        """Exchange an OTP for a session.

        Raises:
            OTPInvalid: OTP did not match.
            OTPExpired: OTP window closed (typical: 5 minutes).
            RateLimited: too many attempts.
            GSTNUnavailable: GSTN downstream issue during exchange.
        """
        ...

    def fetch_gstr2b(
        self, session: Session, gstin: str, period: str
    ) -> dict[str, Any]:
        """Fetch the raw 2B JSON for ``period`` (YYYYMM).

        Returned payload is the vendor's response body. Callers pass it
        straight to :func:`app.ingestion.gstr2b_parser.parse_gstr2b_json`
        (which already handles the two common GSTN top-level shapes).

        Raises:
            SessionExpired: session TTL elapsed or was revoked upstream.
            GSTNUnavailable: GSTN portal is down; retry with backoff.
            RateLimited: honor Retry-After.
            ConsentRevoked: MSME revoked consent on the GSTN portal.
        """
        ...

    def session_status(self, session: Session) -> bool:
        """Cheap health check. Returns True iff the session is usable.

        Adapters SHOULD prefer a lightweight endpoint over
        re-fetching a full 2B payload. If no cheap endpoint exists on the
        vendor, they MAY return :attr:`Session.is_expired` — document
        that choice in the adapter's docstring.
        """
        ...

    def refresh_or_reauth(self, session: Session) -> Session | None:
        """Try to extend ``session`` silently. Return None if not possible.

        Returning None is the "reconnect needed" signal — the caller
        should surface the GSTIN as needing a fresh consent flow. This
        method MUST NOT itself trigger OTPs; that is
        :meth:`initiate_consent`'s job. See UI copy: we never silently
        fail a scheduled pull.

        Raises:
            ConsentRevoked: vendor reports consent explicitly revoked.
            GSTNUnavailable: refresh endpoint down; caller may retry.
        """
        ...
