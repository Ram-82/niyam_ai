"""Unit tests for the taxonomy-aware retry policy."""
from __future__ import annotations

import pytest

from app.gsp import retry
from app.gsp.client import (
    ConsentRevoked,
    GSTNUnavailable,
    OTPExpired,
    OTPInvalid,
    RateLimited,
    SessionExpired,
    UnknownGSPError,
)


def _policy(**over) -> retry.RetryPolicy:
    return retry.RetryPolicy(
        max_attempts=over.get("max_attempts", 3),
        gstn_unavailable_backoff=over.get("gstn_unavailable_backoff", [1, 2, 4]),
        rate_limited_default=over.get("rate_limited_default", 5),
    )


def _fixed_source(seq):
    it = iter(seq)

    def _f():
        item = next(it)
        if isinstance(item, Exception):
            raise item
        return item

    return _f


def test_retries_gstn_unavailable_and_succeeds() -> None:
    fn = _fixed_source([GSTNUnavailable("down"), GSTNUnavailable("still"), "ok"])
    waits: list[int] = []
    r, attempts = retry.run_with_retry(
        fn, policy=_policy(), sleep=lambda s: waits.append(int(s))
    )
    assert r == "ok"
    assert attempts == 3
    assert waits == [1, 2]  # exp backoff [1, 2, 4]; used first two


def test_max_attempts_exhausted_raises_last_error() -> None:
    err = GSTNUnavailable("still down")
    fn = _fixed_source([GSTNUnavailable("down"), err, err])
    with pytest.raises(GSTNUnavailable):
        retry.run_with_retry(fn, policy=_policy(), sleep=lambda s: None)


def test_rate_limited_honors_vendor_retry_after() -> None:
    fn = _fixed_source(
        [RateLimited("slow", retry_after_seconds=42), "ok"]
    )
    waits: list[int] = []
    r, _ = retry.run_with_retry(
        fn, policy=_policy(rate_limited_default=5), sleep=lambda s: waits.append(int(s))
    )
    assert r == "ok"
    assert waits == [42]  # vendor header wins over the default floor


def test_rate_limited_falls_back_to_default_when_no_header() -> None:
    fn = _fixed_source([RateLimited("slow"), "ok"])
    waits: list[int] = []
    retry.run_with_retry(
        fn,
        policy=_policy(rate_limited_default=7),
        sleep=lambda s: waits.append(int(s)),
    )
    assert waits == [7]


@pytest.mark.parametrize(
    "exc",
    [
        OTPInvalid("bad otp"),
        OTPExpired("late"),
        SessionExpired("dead"),
        ConsentRevoked("nope"),
        UnknownGSPError("mystery"),
    ],
)
def test_never_retries_non_retryable(exc) -> None:
    """The frozen policy: nothing outside GSTN_UNAVAILABLE / RATE_LIMITED
    is ever retried. Especially OTP/CONSENT — retrying would either
    re-send SMS or lock the user out on the vendor side."""
    fn = _fixed_source([exc, "ok"])
    with pytest.raises(type(exc)):
        retry.run_with_retry(fn, policy=_policy(), sleep=lambda s: None)


def test_on_retry_callback_receives_wait_seconds() -> None:
    fn = _fixed_source([GSTNUnavailable("down"), "ok"])
    seen = []

    def cb(attempt, err, wait):
        seen.append((attempt, err.kind.value, wait))

    retry.run_with_retry(fn, policy=_policy(), sleep=lambda s: None, on_retry=cb)
    assert seen == [(1, "gstn_unavailable", 1)]
