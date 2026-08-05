"""Adversarial containment tests for test-only security/rate-limit helpers.

These tests fail LOUD if someone weakens the containment of anti-abuse
mutations. They belong with the RLS isolation tests (also in this
security bucket): every failure here is a P0 signal, not a "oh, style
question" signal.

What must remain true:

  1. No symbol named ``clear_initiate_cooldown`` (or any obvious
     synonym) exists in the ``app`` package. That was the specific
     helper moved to ``tests/support/`` in P2.1 Stage C.
  2. No HTTP route, no worker job, no CLI entry point imports
     ``tests.support.lockout_admin``.
  3. The support helper refuses to run without the
     ``NIYAM_ALLOW_TEST_HELPERS=1`` env flag. That flag is set by the
     pytest session, not by app config, so a production process cannot
     inadvertently satisfy it via ``Settings``.

If a future change legitimately needs to reset a cooldown at runtime,
the correct move is a new product feature with its own audit + rate
limits — not to punch a hole in this containment.
"""
from __future__ import annotations

import importlib
import os
import subprocess
from pathlib import Path

import pytest


APP_ROOT = Path(__file__).parent.parent.parent / "app"
BANNED_SYMBOLS = ("clear_initiate_cooldown",)


# ---------------------------------------------------------------------------
# (1) The old symbol must not exist in the app package.
# ---------------------------------------------------------------------------


def test_clear_initiate_cooldown_is_gone_from_app_gsp_lockout() -> None:
    from app.gsp import lockout

    for name in BANNED_SYMBOLS:
        assert not hasattr(lockout, name), (
            f"app.gsp.lockout.{name} was moved to tests/support/lockout_admin.py "
            "in P2.1 Stage C. Re-adding it is a P0 containment regression — "
            "the SMS-flood cooldown must never be resettable from a deployed "
            "process without an audited product path."
        )


def test_no_source_file_under_app_mentions_the_banned_symbols() -> None:
    """grep-style: assert no file under app/ contains ``clear_initiate_cooldown``.

    A comment noting the historical location is fine — but ONLY as a
    NOTE, not as a symbol that could be imported or grep-fished into a
    new caller. This test allows the marker comment we left behind and
    fails on anything else (imports, function defs, HTTP routes, jobs).
    """
    for py in APP_ROOT.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for name in BANNED_SYMBOLS:
            if name not in text:
                continue
            # The only allowed mention: a NOTE comment in gsp/lockout.py.
            lines = [
                ln for ln in text.splitlines()
                if name in ln
            ]
            if py.name == "lockout.py" and py.parent.name == "gsp":
                assert all(ln.lstrip().startswith("#") for ln in lines), (
                    f"{py} contains a non-comment reference to {name!r} — "
                    "in this file only a NOTE comment about the historical "
                    "location is permitted"
                )
                continue
            pytest.fail(
                f"{py} contains {name!r}. That symbol lives in "
                "tests/support/lockout_admin.py — outside the app package. "
                "See P2.1 Stage C for the containment rationale."
            )


# ---------------------------------------------------------------------------
# (2) The support module must not be imported by anything under app/.
# ---------------------------------------------------------------------------


def test_no_app_module_imports_the_test_support_package() -> None:
    """If anyone writes ``from tests.support.<x> import <y>`` inside the
    app package, this test flags it. tests.support ships only inside the
    test tree; a deployed backend can't import it."""
    marker = "tests.support"
    for py in APP_ROOT.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        assert marker not in text, (
            f"{py} imports from {marker}. tests/support/ is test-only by "
            "P2.1 Stage C containment — a deployed backend does not ship it."
        )


# ---------------------------------------------------------------------------
# (3) Env-flag guard: helper refuses to run without NIYAM_ALLOW_TEST_HELPERS=1.
# ---------------------------------------------------------------------------


def test_support_helper_refuses_to_run_without_env_flag(monkeypatch) -> None:
    from tests.support.lockout_admin import (
        TestHelperDisabled,
        clear_gsp_initiate_cooldown_for_gstin,
    )

    monkeypatch.delenv("NIYAM_ALLOW_TEST_HELPERS", raising=False)
    with pytest.raises(TestHelperDisabled):
        clear_gsp_initiate_cooldown_for_gstin("29AAAAA0000A1ZY")


def test_support_helper_runs_with_env_flag_set(monkeypatch) -> None:
    """The positive case — with the env flag set (as pytest itself sets it),
    the helper works. Guards against the env-flag check accidentally
    breaking all downstream cooldown-clearing tests."""
    from tests.support.lockout_admin import clear_gsp_initiate_cooldown_for_gstin

    monkeypatch.setenv("NIYAM_ALLOW_TEST_HELPERS", "1")
    # Should not raise.
    clear_gsp_initiate_cooldown_for_gstin("29AAAAA0000A1ZY")


# ---------------------------------------------------------------------------
# (4) The env flag is NOT declared on app.config.Settings. A prod .env that
#     accidentally sets NIYAM_ALLOW_TEST_HELPERS=1 does not "wire up" the
#     helper because (a) the helper isn't importable from app anyway and
#     (b) Settings never reads it, so no branch inside the app changes
#     behaviour based on it.
# ---------------------------------------------------------------------------


def test_settings_does_not_expose_the_test_helper_flag() -> None:
    from app.config import Settings

    field_names = set(Settings.model_fields.keys())
    assert "niyam_allow_test_helpers" not in {n.lower() for n in field_names}, (
        "The NIYAM_ALLOW_TEST_HELPERS env var must NEVER appear on "
        "app.config.Settings. If it does, a prod .env that sets the flag "
        "could accidentally arm the test-only helpers via a Settings read."
    )


# ---------------------------------------------------------------------------
# (5) The support module can be imported from a fresh Python process ONLY
#     when tests/ is on the path — i.e. a production deployment that
#     packages only the app/ tree cannot reach it.
#
#     This is a light smoke check: assert tests/support/lockout_admin.py
#     really lives under tests/ (not accidentally re-added to app/).
# ---------------------------------------------------------------------------


def test_support_helper_lives_under_tests_not_under_app() -> None:
    from tests.support import lockout_admin

    module_path = Path(lockout_admin.__file__).resolve()
    assert "tests/support" in str(module_path), (
        f"lockout_admin resolved to {module_path}. It must live under "
        "tests/support/ — the pyproject packages.find pattern includes "
        "only app*, so tests/ never ships in a deployment."
    )
    assert "/app/" not in str(module_path).replace("/app/tests/", "/"), (
        f"lockout_admin resolved somewhere inside the app package: {module_path}"
    )
