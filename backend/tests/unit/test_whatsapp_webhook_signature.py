"""Meta webhook HMAC verification tests.

If the signature verifier ever misses a tamper, an attacker can spoof
delivery status callbacks and mark messages read/failed at will. The
tests below assert every failure path returns False and the happy path
returns True.
"""
from __future__ import annotations

import hashlib
import hmac

import pytest

from app.whatsapp.webhook import parse_status_events, verify_signature


APP_SECRET = "supersecret-test-only"


def _sign(body: bytes, secret: str = APP_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class TestVerifySignature:
    def test_valid_signature_returns_true(self) -> None:
        body = b'{"entry":[]}'
        assert verify_signature(
            body=body, header_value=_sign(body), app_secret=APP_SECRET
        ) is True

    def test_missing_header_returns_false(self) -> None:
        body = b'{"entry":[]}'
        assert verify_signature(
            body=body, header_value=None, app_secret=APP_SECRET
        ) is False

    def test_wrong_prefix_returns_false(self) -> None:
        body = b'{"entry":[]}'
        digest = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
        # Meta uses 'sha256='; sha1 or missing prefix should fail.
        assert verify_signature(
            body=body, header_value=f"sha1={digest}", app_secret=APP_SECRET
        ) is False

    def test_tampered_body_returns_false(self) -> None:
        original = b'{"entry":[]}'
        tampered = b'{"entry":[{"tampered":true}]}'
        # Signature was computed on the original but header sent with tampered body.
        assert verify_signature(
            body=tampered, header_value=_sign(original), app_secret=APP_SECRET
        ) is False

    def test_empty_secret_returns_false(self) -> None:
        """Empty secret must NOT accept everything — that would be a
        catastrophic misconfiguration surface."""
        body = b'{"entry":[]}'
        assert verify_signature(
            body=body, header_value=_sign(body, "anything"), app_secret=""
        ) is False

    def test_wrong_secret_returns_false(self) -> None:
        body = b'{"entry":[]}'
        assert verify_signature(
            body=body, header_value=_sign(body, "different-secret"), app_secret=APP_SECRET
        ) is False

    def test_empty_after_prefix_returns_false(self) -> None:
        assert verify_signature(
            body=b"", header_value="sha256=", app_secret=APP_SECRET
        ) is False


class TestParseStatusEvents:
    def test_extracts_delivered_and_read(self) -> None:
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": "wamid.ABC",
                                        "status": "delivered",
                                        "timestamp": "1700000000",
                                    },
                                    {
                                        "id": "wamid.ABC",
                                        "status": "read",
                                        "timestamp": "1700000060",
                                    },
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        events = parse_status_events(payload)
        assert [(e.provider_message_id, e.status) for e in events] == [
            ("wamid.ABC", "delivered"),
            ("wamid.ABC", "read"),
        ]

    def test_failed_carries_error_kind_and_message(self) -> None:
        payload = {
            "entry": [
                {
                    "changes": [
                        {
                            "value": {
                                "statuses": [
                                    {
                                        "id": "wamid.FAIL",
                                        "status": "failed",
                                        "timestamp": "1700000000",
                                        "errors": [
                                            {"code": 131047, "title": "Re-engagement message"}
                                        ],
                                    }
                                ]
                            }
                        }
                    ]
                }
            ]
        }
        events = parse_status_events(payload)
        assert len(events) == 1
        assert events[0].error_kind == "131047"
        assert events[0].error_message == "Re-engagement message"

    def test_empty_payload_returns_empty(self) -> None:
        assert parse_status_events({}) == []
        assert parse_status_events({"entry": []}) == []

    def test_ignores_non_status_events(self) -> None:
        payload = {
            "entry": [
                {"changes": [{"value": {"messages": [{"from": "1234"}]}}]}
            ]
        }
        assert parse_status_events(payload) == []
