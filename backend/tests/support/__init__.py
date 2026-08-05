"""Test-only support helpers.

Nothing in this package is imported by the ``app`` package. If it is, the
adversarial containment tests
(``tests/security/test_no_test_helpers_in_app.py``) fail. That is the
whole point — helpers here can mutate security or rate-limit state, and
they must never be reachable from a deployed process.
"""
