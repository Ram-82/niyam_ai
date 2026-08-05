"""In-memory Transport for dev + tests.

Deterministic ``provider_message_id`` derived from a monotonically-
increasing counter so tests can assert on the value directly. Never
touches the network.

Failure injection: setting ``next_error`` on the module instance causes
the NEXT ``send_template`` call to raise that error and clear the
attribute. Used by tests to exercise the taxonomy without needing
Meta to actually return a 429 / 5xx.
"""
from __future__ import annotations

import itertools
from typing import Any, Optional

from app.whatsapp.types import (
    SendResult,
    TemplateLanguage,
    WhatsAppError,
    is_valid_e164,
    InvalidNumber,
)


class MockTransport:
    provider = "mock"

    def __init__(self) -> None:
        self._counter = itertools.count(1)
        self.sent: list[dict[str, Any]] = []
        self.next_error: Optional[WhatsAppError] = None

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
            # Enforce the format check here too — the real Meta API 400s
            # on invalid, so the mock does the same for parity.
            raise InvalidNumber(
                f"{to_e164!r} is not an E.164 phone number"
            )
        if self.next_error is not None:
            err = self.next_error
            self.next_error = None
            raise err
        n = next(self._counter)
        message_id = f"wamid.mock.{n:06d}"
        self.sent.append(
            {
                "to_e164": to_e164,
                "template_name": template_name,
                "template_lang": template_lang,
                "media_size": len(media_bytes) if media_bytes else 0,
                "media_mime": media_mime,
                "components": components or [],
                "message_id": message_id,
            }
        )
        return SendResult(
            provider=self.provider,
            provider_message_id=message_id,
            status="sent",
        )


# Module-level singleton so tests can reach in and inject failures
# without threading the transport through fixtures. Service.get_transport
# returns this instance in mock mode.
_singleton = MockTransport()


def get_singleton() -> MockTransport:
    return _singleton
