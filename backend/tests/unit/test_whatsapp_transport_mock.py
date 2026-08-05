"""MockTransport unit tests.

Focused on the parity properties the mock must uphold so tests using it
match real Meta behaviour:

* E.164 rejection matches real 400 behaviour.
* Deterministic message_ids so integration tests can assert on them.
* Failure injection via next_error clears itself so subsequent calls
  do not accidentally re-fire.
"""
from __future__ import annotations

import pytest

from app.whatsapp.transport_mock import MockTransport
from app.whatsapp.types import (
    InvalidNumber,
    RateLimited,
    SendResult,
    WhatsAppErrorKind,
)


def test_valid_e164_returns_deterministic_id() -> None:
    t = MockTransport()
    r1 = t.send_template(
        to_e164="+919876543210",
        template_name="niyam_report_v1",
        template_lang="en_US",
    )
    r2 = t.send_template(
        to_e164="+919876543210",
        template_name="niyam_report_v1",
        template_lang="en_US",
    )
    assert r1.provider == "mock"
    assert r1.provider_message_id == "wamid.mock.000001"
    assert r2.provider_message_id == "wamid.mock.000002"
    assert isinstance(r1, SendResult)


def test_invalid_e164_raises_invalid_number() -> None:
    t = MockTransport()
    with pytest.raises(InvalidNumber):
        t.send_template(
            to_e164="9876543210",  # missing '+'
            template_name="niyam_report_v1",
            template_lang="en_US",
        )


def test_media_size_is_tracked() -> None:
    t = MockTransport()
    t.send_template(
        to_e164="+919876543210",
        template_name="niyam_report_v1",
        template_lang="en_US",
        media_bytes=b"%PDF-fake",
        media_mime="application/pdf",
    )
    assert t.sent[-1]["media_size"] == len(b"%PDF-fake")
    assert t.sent[-1]["media_mime"] == "application/pdf"


def test_next_error_fires_once_then_clears() -> None:
    t = MockTransport()
    t.next_error = RateLimited("throttled", http_status=429, retry_after_seconds=30)
    with pytest.raises(RateLimited) as exc:
        t.send_template(
            to_e164="+919876543210",
            template_name="niyam_report_v1",
            template_lang="en_US",
        )
    assert exc.value.retry_after_seconds == 30
    # Second call should proceed normally.
    r = t.send_template(
        to_e164="+919876543210",
        template_name="niyam_report_v1",
        template_lang="en_US",
    )
    assert r.provider_message_id.startswith("wamid.mock.")


def test_error_kind_taxonomy() -> None:
    t = MockTransport()
    t.next_error = InvalidNumber("bad")
    with pytest.raises(InvalidNumber) as exc:
        t.send_template(
            to_e164="+919876543210",
            template_name="niyam_report_v1",
            template_lang="en_US",
        )
    assert exc.value.kind == WhatsAppErrorKind.INVALID_NUMBER
