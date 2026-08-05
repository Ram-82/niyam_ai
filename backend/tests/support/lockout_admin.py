"""Test-only lockout / rate-limit admin helpers.

These functions mutate anti-abuse state. They exist because tests need to
run many consent-flow scenarios per second without waiting for the
one-hour SMS-flood cooldown to roll off. Nothing in the ``app`` package
imports this module; nothing in a deployed process reaches it.

Containment layers:

  1. **Physical location.** Lives in ``tests/support/``, which is outside
     the ``app`` package. A ``pip install`` of the backend package (see
     ``pyproject.toml`` ``[tool.setuptools.packages.find] include =
     ["app*"]``) does not ship this file.

  2. **Env-flag guard.** Every function here reads
     ``NIYAM_ALLOW_TEST_HELPERS`` from the OS environment and raises
     :class:`RuntimeError` unless it equals ``"1"``. The flag is set
     once, session-scoped, by ``tests/conftest.py``. It is NOT declared
     on :class:`app.config.Settings`, so a production config that
     accidentally set the env var could still not trigger these helpers
     through the app — only test code that imports this module can.

  3. **Adversarial containment test.** ``tests/security/`` asserts
     - the helper is NOT importable from ``app.gsp.lockout`` any more
     - no source file under ``app/`` mentions the helper's name
     Both fail loud if anyone re-adds the shortcut.

If any of the three layers is ever weakened, the fourth line of defence
is that the helper writes to ``audit_log`` when it can identify a
firm_id. See :func:`clear_gsp_initiate_cooldown_for_gstin` — it takes an
optional ``audit_ctx`` and, when supplied, records the mutation with
actor + GSTIN + timestamp so misuse is traceable.
"""
from __future__ import annotations

import os
import uuid
from typing import Optional


_ALLOW_ENV = "NIYAM_ALLOW_TEST_HELPERS"


class TestHelperDisabled(RuntimeError):
    """Raised when a test-only helper is invoked without the env flag set.

    In practice this only fires if someone imports this module from
    outside pytest — the pytest session sets the flag in conftest before
    any test can call in.
    """


def _require_flag() -> None:
    if os.getenv(_ALLOW_ENV) != "1":
        raise TestHelperDisabled(
            f"{_ALLOW_ENV}=1 is required to use tests.support.lockout_admin. "
            "This helper is test-only and must never run in a deployed "
            "environment. If you see this in production logs, treat it as "
            "a P0 security incident."
        )


def clear_gsp_initiate_cooldown_for_gstin(
    gstin: str,
    *,
    audit_ctx: Optional["AuditCtx"] = None,
) -> None:
    """Clear the per-GSTIN SMS-flood cooldown so a test can re-run
    ``initiate_consent`` immediately.

    ``audit_ctx``, when supplied, writes one ``audit_log`` row so the
    mutation is traceable. Tests that don't care about audit provenance
    can omit it. Any hypothetical deployed caller MUST supply it — the
    audit row is the trail investigators would follow.
    """
    _require_flag()
    # Import lazily so pytest collection doesn't reach into app modules
    # before their guard checks have run.
    from app.gsp.lockout import _initiate_key, _redis
    _redis.delete(_initiate_key(gstin))
    if audit_ctx is not None:
        audit_ctx.write(gstin)


class AuditCtx:
    """Optional container that writes an audit_log row when a test-only
    mutation runs. Constructed by the caller so the caller decides who
    the actor is."""

    def __init__(
        self,
        firm_id: uuid.UUID | str,
        actor_user_id: Optional[uuid.UUID | str],
        reason: str,
    ) -> None:
        self.firm_id = firm_id
        self.actor_user_id = actor_user_id
        self.reason = reason

    def write(self, gstin: str) -> None:
        from datetime import datetime, timezone

        from app.auth import audit
        from app.db import firm_scoped_session

        with firm_scoped_session(self.firm_id) as db:
            audit.record(
                db,
                firm_id=self.firm_id,
                actor_user_id=self.actor_user_id,
                action="test_helper.clear_gsp_initiate_cooldown",
                entity_type="test_helper",
                entity_id=None,
                metadata={
                    "gstin": gstin,
                    "reason": self.reason,
                    "at": datetime.now(tz=timezone.utc).isoformat(),
                    "warning": (
                        "This row was written by a test-only helper. "
                        "In production this action is impossible; if you "
                        "see this row, investigate."
                    ),
                },
            )
