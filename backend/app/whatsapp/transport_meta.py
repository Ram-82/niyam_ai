"""Meta (Facebook) WhatsApp Business Cloud API adapter.

This is P2 scaffolding — the real Meta onboarding pipeline (Facebook
Business Manager, WABA phone number verification, template review) is
a multi-week bureaucratic sequence. Until we hold pilot credentials
this adapter is code-reviewable but not test-exercised end-to-end.

What is here:

* ``send_template`` builds the Cloud API payload per Meta's Graph API
  v20 template-message schema and POSTs it via httpx.
* Media (the PDF 2-pager) is uploaded FIRST via /media, then the
  returned media_id is threaded into the template's header component.
  Two API calls per send; both are metered against the WABA's rate
  limit.
* Errors are mapped to the :class:`WhatsAppError` taxonomy so the
  service layer can react in one place.

What is NOT here (deferred until Meta creds land):

* Rate-limit backoff — the retry layer we ship in ``app.gsp.retry`` is
  the pattern to copy; do it when we can see real vendor timing.
* Media reuse for identical bytes across sends. Not important at demo
  scale; a hash-keyed cache is a P3 optimisation.
"""
from __future__ import annotations

import io
import logging
from typing import Any, Optional

from app.whatsapp.types import (
    InvalidNumber,
    MetaServerError,
    RateLimited,
    SendResult,
    TemplateLanguage,
    TemplateNotApproved,
    Transport,
    WhatsAppError,
    is_valid_e164,
)


log = logging.getLogger("niyam.whatsapp.meta")


class MetaTransport:
    provider = "meta"

    def __init__(
        self,
        *,
        access_token: str,
        phone_number_id: str,
        graph_version: str = "v20.0",
        base_url: str = "https://graph.facebook.com",
        timeout_seconds: float = 15.0,
    ) -> None:
        if not access_token:
            raise WhatsAppError("meta transport: access_token is empty")
        if not phone_number_id:
            raise WhatsAppError("meta transport: phone_number_id is empty")
        self._access_token = access_token
        self._phone_number_id = phone_number_id
        self._graph_version = graph_version
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    def _endpoint(self, path: str) -> str:
        return f"{self._base_url}/{self._graph_version}/{path}"

    def _upload_media(self, media_bytes: bytes, media_mime: str) -> str:
        """POST /{phone_number_id}/media — returns media_id."""
        import httpx

        files = {
            "file": (
                "niyam_report.pdf",
                io.BytesIO(media_bytes),
                media_mime,
            ),
            "type": (None, media_mime),
            "messaging_product": (None, "whatsapp"),
        }
        try:
            r = httpx.post(
                self._endpoint(f"{self._phone_number_id}/media"),
                headers=self._headers(),
                files=files,
                timeout=self._timeout,
            )
        except httpx.HTTPError as e:
            raise MetaServerError(f"meta media upload transport error: {e}")
        _translate_status(r)
        return r.json()["id"]

    def send_template(
        self,
        *,
        to_e164: str,
        template_name: str,
        template_lang: TemplateLanguage,
        media_bytes: Optional[bytes] = None,
        media_mime: Optional[str] = None,
        components: Optional[list[dict[str, Any]]] = None,
    ) -> SendResult:
        if not is_valid_e164(to_e164):
            raise InvalidNumber(f"{to_e164!r} is not an E.164 phone number")

        import httpx

        # Build template components. If a media attachment was passed,
        # upload it and prepend a header/document component.
        payload_components = list(components or [])
        if media_bytes is not None:
            if media_mime is None:
                media_mime = "application/pdf"
            media_id = self._upload_media(media_bytes, media_mime)
            payload_components.insert(
                0,
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "document",
                            "document": {
                                "id": media_id,
                                "filename": "niyam_report.pdf",
                            },
                        }
                    ],
                },
            )

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            # Meta expects the E.164 without the leading '+'.
            "to": to_e164.lstrip("+"),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": template_lang},
                "components": payload_components,
            },
        }
        try:
            r = httpx.post(
                self._endpoint(f"{self._phone_number_id}/messages"),
                headers={
                    **self._headers(),
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=self._timeout,
            )
        except httpx.HTTPError as e:
            raise MetaServerError(f"meta send transport error: {e}")
        _translate_status(r)
        # Cloud API returns {"messages": [{"id": "wamid.XXX"}], ...}
        message_id = r.json()["messages"][0]["id"]
        return SendResult(
            provider=self.provider,
            provider_message_id=message_id,
            status="sent",
        )


def _translate_status(response) -> None:
    """Map Meta HTTP status → typed exception. Non-error status returns."""
    if 200 <= response.status_code < 300:
        return
    body: dict = {}
    try:
        body = response.json() or {}
    except Exception:  # pragma: no cover — meta always returns JSON
        pass
    err = body.get("error") or {}
    code = err.get("code")
    subcode = err.get("error_subcode")
    message = err.get("message") or f"http {response.status_code}"

    # Well-known Meta error codes (subset — the taxonomy we act on).
    # Full list: https://developers.facebook.com/docs/whatsapp/cloud-api/support/error-codes
    if response.status_code == 429 or code == 130429:
        retry = response.headers.get("Retry-After")
        raise RateLimited(
            message,
            http_status=response.status_code,
            retry_after_seconds=int(retry) if retry else None,
        )
    if code == 132000 or code == 132001 or subcode == 2494077:
        raise TemplateNotApproved(message, http_status=response.status_code)
    if code == 131026 or code == 131047 or code == 100:
        raise InvalidNumber(message, http_status=response.status_code)
    if response.status_code >= 500:
        raise MetaServerError(message, http_status=response.status_code)
    raise WhatsAppError(
        f"meta unmapped error code={code} subcode={subcode}: {message}",
        http_status=response.status_code,
    )
