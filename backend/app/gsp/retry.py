"""Retry policy for GSP pull calls, wired to the error taxonomy.

Rules (frozen — every deviation is a bug):

* ``GSTN_UNAVAILABLE`` — retry, exponential backoff from the rule pack
  (``gsp.retry.gstn_unavailable_backoff_seconds``), up to
  ``gsp.retry.max_attempts`` total attempts.
* ``RATE_LIMITED`` — retry, but the vendor's ``Retry-After`` header wins
  when present (surfaced as ``retry_after_seconds`` on the exception).
  When the vendor sends no header, fall back to
  ``gsp.retry.rate_limited_default_seconds``.
* Every other kind — including ``OTP_INVALID``, ``OTP_EXPIRED``,
  ``SESSION_EXPIRED``, ``CONSENT_REVOKED``, ``UNKNOWN`` — never retried.
  The caller must decide (reconnect UI, propagate to the CA, etc.).

Never applied to the consent handshake; only wraps data-fetch calls
(``fetch_gstr2b``, ``session_status``, ``refresh_or_reauth``). Retrying
the consent handshake would send extra OTP SMSes — the cooldown in
:mod:`app.gsp.lockout` prevents that on the initiate side but retries
here would sneak past it.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, TypeVar

from app.gsp.client import (
    GSPError,
    GSPErrorKind,
    GSTNUnavailable,
    RateLimited,
)
from app.rules.pack import get_active_rule_pack


log = logging.getLogger("niyam.gsp.retry")


T = TypeVar("T")


class RetryPolicy:
    """Snapshot of the retry knobs from the active rule pack."""

    def __init__(
        self,
        max_attempts: int,
        gstn_unavailable_backoff: list[int],
        rate_limited_default: int,
    ) -> None:
        self.max_attempts = max(1, int(max_attempts))
        self.gstn_unavailable_backoff = [int(x) for x in gstn_unavailable_backoff]
        self.rate_limited_default = int(rate_limited_default)


def load_policy() -> RetryPolicy:
    pack = get_active_rule_pack()
    r = (pack.payload.get("gsp") or {}).get("retry") or {}
    return RetryPolicy(
        max_attempts=r.get("max_attempts", 3),
        gstn_unavailable_backoff=r.get(
            "gstn_unavailable_backoff_seconds", [30, 120, 600]
        ),
        rate_limited_default=r.get("rate_limited_default_seconds", 30),
    )


def _wait_seconds(policy: RetryPolicy, err: GSPError, attempt_idx: int) -> int:
    """How long to sleep before the (attempt_idx+1)th attempt."""
    if isinstance(err, RateLimited):
        if err.retry_after_seconds and err.retry_after_seconds > 0:
            return err.retry_after_seconds
        return policy.rate_limited_default
    if isinstance(err, GSTNUnavailable):
        backoff = policy.gstn_unavailable_backoff
        if not backoff:
            return 30
        return backoff[min(attempt_idx, len(backoff) - 1)]
    raise AssertionError(
        f"_wait_seconds called with non-retryable kind={err.kind}"
    )


def is_retryable(err: GSPError) -> bool:
    return err.kind in (GSPErrorKind.GSTN_UNAVAILABLE, GSPErrorKind.RATE_LIMITED)


def run_with_retry(
    fn: Callable[[], T],
    *,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] | None = None,
    on_retry: Callable[[int, GSPError, int], None] | None = None,
) -> tuple[T, int]:
    """Invoke ``fn`` with the taxonomy-aware retry policy.

    Returns ``(result, attempts_taken)``. Non-retryable errors bubble
    on the first raise. ``on_retry(attempt_index, error, wait_seconds)``
    is called between attempts — used by the pull path to mark the
    ``gsp_pull_attempt`` row as ``retry_scheduled`` with ``next_retry_at``.

    ``sleep`` is injectable so tests don't actually block.
    """
    if policy is None:
        policy = load_policy()
    # Look up time.sleep at call time so tests can monkey-patch it.
    if sleep is None:
        sleep = time.sleep

    for attempt in range(policy.max_attempts):
        try:
            result = fn()
            return result, attempt + 1
        except GSPError as e:
            if not is_retryable(e):
                raise
            if attempt + 1 >= policy.max_attempts:
                raise
            wait = _wait_seconds(policy, e, attempt)
            if on_retry is not None:
                on_retry(attempt + 1, e, wait)
            log.info(
                "gsp.retry kind=%s attempt=%d/%d wait=%ds",
                e.kind.value,
                attempt + 1,
                policy.max_attempts,
                wait,
            )
            sleep(wait)
    raise AssertionError("unreachable")  # loop exits via return or raise
